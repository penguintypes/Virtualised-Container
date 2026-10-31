let me = null;
let feed = [];
let adminList = [];
let currentBlogId = null;
let readerFrom = "home";
let searchTerm = "";

const $ = (id) => document.getElementById(id);
const PAGES = ["home", "myblogs", "write", "reader", "account"];

function escapeHTML(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
}

function formatDate(value) {
    return new Date(value).toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric"
    });
}

async function readJson(response) {
    const text = await response.text();

    try {
        return JSON.parse(text);
    } catch (_) {
        throw new Error("Server is still starting, try again in a few seconds.");
    }
}

async function api(path, method = "GET", body) {
    const options = { method, headers: {} };

    if (body !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(body);
    }

    const response = await fetch(path, options);
    const data = await readJson(response);

    if (!response.ok) {
        throw new Error(data.message || "Request failed.");
    }

    return data;
}

function notify(message, isError = false) {
    const toast = $("toast");
    toast.textContent = message;
    toast.className = "toast show" + (isError ? " err" : "");
    clearTimeout(notify.timer);
    notify.timer = setTimeout(() => {
        toast.className = "toast";
    }, 3500);
}

function askModal({ title, message = "", fields = [], confirmText = "Confirm", danger = false }) {
    return new Promise((resolve) => {
        $("modalTitle").textContent = title;
        $("modalMessage").textContent = message;
        $("modalFields").innerHTML = fields.map((field) =>
            `<label for="mf_${field.id}">${escapeHTML(field.label)}</label>` +
            `<input id="mf_${field.id}" type="${field.type || "text"}" autocomplete="off">`
        ).join("");

        const ok = $("modalOk");
        ok.textContent = confirmText;
        ok.className = "primary-btn" + (danger ? " danger-btn" : "");
        $("modalOverlay").hidden = false;

        if (fields.length) {
            $("mf_" + fields[0].id).focus();
        }

        const finish = (value) => {
            $("modalOverlay").hidden = true;
            ok.onclick = null;
            $("modalCancel").onclick = null;
            resolve(value);
        };

        ok.onclick = () => {
            const values = {};
            fields.forEach((field) => {
                values[field.id] = $("mf_" + field.id).value;
            });
            finish(values);
        };

        $("modalCancel").onclick = () => finish(null);
    });
}

function setUser(user) {
    me = user;
    document.body.classList.toggle("guest-mode", !user);
    $("accountBtn").hidden = !user;

    if (user) {
        $("accountEmail").textContent = user.email;
        $("accountAvatar").textContent = (user.username || "?").charAt(0).toUpperCase();
    }
}

async function loadMe() {
    try {
        const data = await api("/api/me");
        setUser(data.user);
    } catch (_) {
        setUser(null);
    }
}

async function loadFeed() {
    try {
        const data = await api("/api/blogs/all");
        feed = data.blogs.map((blog) => ({
            ...blog,
            views: Number(blog.views) || 0,
            comment_count: Number(blog.comment_count) || 0
        }));
        return true;
    } catch (error) {
        feed = [];
        notify(error.message, true);
        return false;
    }
}

function showSection(id) {
    if (!me && ["myblogs", "write", "account"].includes(id)) {
        openAuth("login", "Please log in to continue.");
        return;
    }

    PAGES.forEach((page) => $(page).classList.toggle("active", page === id));

    const navId = id === "write" ? "myblogs" : id === "reader" ? readerFrom : id;
    document.querySelectorAll(".nav-btn").forEach((button) => {
        button.classList.toggle("active", button.dataset.section === navId);
    });
    $("accountBtn").classList.toggle("active", id === "account");

    if (id === "home") renderHome();
    if (id === "myblogs") renderMine();
    if (id === "account") renderAccount();

    $("sidebar").classList.remove("open");
    window.scrollTo(0, 0);
}

function blogCard(blog) {
    const canDelete = me && (blog.user_id === me.id || me.is_admin);
    const preview = blog.content.length > 140 ? blog.content.substring(0, 140) + "..." : blog.content;

    return `
        <div class="my-blog-card">
            <h2>${escapeHTML(blog.title)}</h2>
            <p class="blog-preview">${escapeHTML(preview)}</p>
            <div class="blog-card-stats">
                <span>✍️ ${escapeHTML(blog.author)}</span>
                <span>👁️ ${blog.views}</span>
                <span>💬 ${blog.comment_count}</span>
                <span>📅 ${formatDate(blog.created_at)}</span>
            </div>
            <div class="blog-card-buttons">
                <button class="read-btn" data-read="${blog.id}">Read Blog</button>
                ${canDelete ? `<button class="delete-btn" data-del="${blog.id}">Delete</button>` : ""}
            </div>
        </div>`;
}

function renderHome() {
    const query = searchTerm.trim().toLowerCase();
    const list = feed.filter((blog) =>
        !query ||
        blog.title.toLowerCase().includes(query) ||
        blog.author.toLowerCase().includes(query)
    );

    $("homeBlogs").innerHTML = list.length
        ? list.map(blogCard).join("")
        : `<div class="empty-state">
               <div>📚</div>
               <h3>${feed.length ? "No matching blogs" : "No blogs yet"}</h3>
               <p>${feed.length ? "Try a different search." : "Posts will appear here."}</p>
           </div>`;
}

function renderMine() {
    const mine = me ? feed.filter((blog) => blog.user_id === me.id) : [];

    $("totalBlogs").textContent = mine.length;
    $("totalViews").textContent = mine.reduce((sum, blog) => sum + blog.views, 0);
    $("totalComments").textContent = mine.reduce((sum, blog) => sum + blog.comment_count, 0);

    $("myBlogs").innerHTML = mine.length
        ? mine.map(blogCard).join("")
        : `<div class="empty-state">
               <div>📝</div>
               <h3>No blogs yet</h3>
               <p>Start writing your first blog.</p>
               <button class="primary-btn" data-newblog="1">Write Your First Blog</button>
           </div>`;
}

function refreshLists() {
    if ($("myblogs").classList.contains("active")) {
        renderMine();
    } else if ($("home").classList.contains("active")) {
        renderHome();
    }
}

async function openBlog(id) {
    const blog = feed.find((item) => item.id === id);

    if (!blog) {
        return;
    }

    readerFrom = $("myblogs").classList.contains("active") ? "myblogs" : "home";
    currentBlogId = id;

    if (me) {
        try {
            const result = await api(`/api/blogs/${id}/view`, "POST");

            if (result.views != null) {
                blog.views = Number(result.views);
            }
        } catch (_) {
            // View counting is best effort.
        }
    }

    try {
        const data = await api(`/api/blogs/${id}/comments`);
        blog.comments = data.comments.map((comment) => ({
            id: comment.id,
            user_id: comment.user_id, name: comment.name,
            text: comment.content,
            date: formatDate(comment.created_at)
        }));
    } catch (error) {
        blog.comments = [];
        notify(error.message, true);
    }

    $("readerTitle").textContent = blog.title;
    $("readerContent").textContent = blog.content;
    $("readerAuthor").textContent = "By " + blog.author;
    $("readerDate").textContent = formatDate(blog.created_at);
    $("readerViews").textContent = `${blog.views} views`;
    $("commentForm").hidden = !me;
    $("commentLogin").hidden = Boolean(me);

    displayComments(blog);
    showSection("reader");
}

function displayComments(blog) {
    $("commentCount").textContent = blog.comments.length;

    $("commentsList").innerHTML = blog.comments.length
        ? blog.comments.map((comment) => `
            <div class="comment">
                <div class="comment-header">
                    <span class="comment-name">${escapeHTML(comment.name)}</span>
                    <span class="comment-date">${comment.date}</span>${me && (comment.user_id === me.id || blog.user_id === me.id || me.is_admin) ? `<button type="button" class="comment-del" data-delcomment="${comment.id}">Delete</button>` : ""}
                </div>
                <p>${escapeHTML(comment.text)}</p>
            </div>`).join("")
        : `<div class="empty-state"><p>No comments yet. Be the first!</p></div>`;
}

async function addComment() {
    const blog = feed.find((item) => item.id === currentBlogId);

    if (!blog) {
        return;
    }

    if (!me) {
        openAuth("login", "Please log in to comment.");
        return;
    }

    const text = $("commentText").value.trim();

    if (!text) {
        notify("Please write a comment.", true);
        return;
    }

    try {
        const data = await api(`/api/blogs/${currentBlogId}/comments`, "POST", { text });
        blog.comments.push({ ...data.comment, user_id: me.id });
        blog.comment_count += 1;
        $("commentText").value = "";
        displayComments(blog);
    } catch (error) {
        notify(error.message, true);
    }
}

async function publishBlog() {
    const title = $("blogTitle").value.trim();
    const content = $("blogContent").value.trim();

    if (!title) {
        notify("Please enter a blog title.", true);
        return;
    }

    if (!content) {
        notify("Please write something in your blog.", true);
        return;
    }

    if (!me) {
        openAuth("login", "Please log in to publish.");
        return;
    }

    try {
        await api("/api/blogs", "POST", { title, content });
        $("blogTitle").value = "";
        $("blogContent").value = "";
        $("charCount").textContent = "0 characters";
        await loadFeed();
        notify("Blog published.");
        showSection("myblogs");
    } catch (error) {
        notify(error.message, true);
    }
}

async function deleteBlog(id) {
    const ok = await askModal({
        title: "Delete blog?",
        message: "This also removes its comments. This cannot be undone.",
        confirmText: "Delete",
        danger: true
    });

    if (!ok) {
        return;
    }

    try {
        await api(`/api/blogs/${id}`, "DELETE");
        notify("Blog deleted.");
        await loadFeed();
        refreshLists();
    } catch (error) {
        notify(error.message, true);
    }
}

function openAuth(mode, message = "") {
    document.body.classList.add("auth-open");
    $("authForms").hidden = false;
    $("registerForm").hidden = mode !== "register";
    $("loginForm").hidden = mode !== "login";
    $("authMessage").textContent = message;
    $("authForms").scrollIntoView({ behavior: "smooth" });
}

function closeAuth() {
    $("authForms").hidden = true;
    document.body.classList.remove("auth-open");
}

function renderAccount() {
    $("accUsername").value = me.username;
    $("accEmail").value = me.email;
    $("adminCard").hidden = !me.is_admin;
    /* admin-tag */
    $("deleteAccountBtn").hidden = Boolean(me.is_admin);
    if (me.is_admin) {
        $("deleteAccountBtn").previousElementSibling.textContent = "Admin accounts cannot be deleted here.";
    }

    if (me.is_admin) {
        loadAdminUsers();
    }
}

async function loadAdminUsers() {
    try {
        const data = await api("/api/admin/users");
        adminList = data.users;
        $("adminUsers").innerHTML = adminList.map((user) => `
            <tr>
                <td>${user.id}</td>
                <td>${escapeHTML(user.username)}${user.email.toLowerCase() === me.email.toLowerCase() ? ' <span style="background:#7650d9;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;margin-left:6px;">Admin</span>' : ""}</td>
                <td>${escapeHTML(user.email)}</td>
                <td>${user.blog_count}</td>
                <td class="admin-actions">
                    <button class="read-btn" data-reset="${user.id}">Reset password</button>
                    ${user.id === me.id ? "" : `<button class="delete-btn" data-deluser="${user.id}">Delete</button>`}
                </td>
            </tr>`).join("");
    } catch (error) {
        notify(error.message, true);
    }
}

async function resetUserPassword(id) {
    const user = adminList.find((item) => item.id === id);

    if (!user) {
        return;
    }

    const values = await askModal({
        title: `Reset password for ${user.username}`,
        message: "Set a new password for this user.",
        fields: [{ id: "pw", label: "New password (8–72 characters)", type: "password" }],
        confirmText: "Reset password"
    });

    if (!values) {
        return;
    }

    try {
        await api(`/api/admin/users/${id}/password`, "POST", { newPassword: values.pw });
        notify("Password reset.");
    } catch (error) {
        notify(error.message, true);
    }
}

async function deleteUser(id) {
    const user = adminList.find((item) => item.id === id);

    if (!user) {
        return;
    }

    const ok = await askModal({
        title: `Delete ${user.username}?`,
        message: "This deletes the user, their blogs and their comments.",
        confirmText: "Delete user",
        danger: true
    });

    if (!ok) {
        return;
    }

    try {
        await api(`/api/admin/users/${id}`, "DELETE");
        notify("User deleted.");
        await loadFeed();
        await loadAdminUsers();
    } catch (error) {
        notify(error.message, true);
    }
}

document.addEventListener("click", (event) => {
    const read = event.target.closest("[data-read]");
    const del = event.target.closest("[data-del]");
    const reset = event.target.closest("[data-reset]");
    const deluser = event.target.closest("[data-deluser]");

    if (read) openBlog(Number(read.dataset.read));
    else if (del) deleteBlog(Number(del.dataset.del));
    else if (reset) resetUserPassword(Number(reset.dataset.reset));
    else if (deluser) deleteUser(Number(deluser.dataset.deluser));
    else if (event.target.closest("[data-newblog]")) showSection("write");

    const sidebar = $("sidebar");

    if (
        sidebar.classList.contains("open") &&
        !sidebar.contains(event.target) &&
        event.target.id !== "menuBtn"
    ) {
        sidebar.classList.remove("open");
    }
});

document.querySelectorAll(".nav-btn").forEach((button) => {
    button.addEventListener("click", () => showSection(button.dataset.section));
});

$("menuBtn").addEventListener("click", () => $("sidebar").classList.toggle("open"));
$("closeSidebar").addEventListener("click", () => $("sidebar").classList.remove("open"));
$("accountBtn").addEventListener("click", () => showSection("account"));
$("newBlogBtn").addEventListener("click", () => showSection("write"));
$("cancelWriteBtn").addEventListener("click", () => showSection("myblogs"));
$("publishBtn").addEventListener("click", publishBlog);
$("readerBack").addEventListener("click", () => showSection(readerFrom));
$("postCommentBtn").addEventListener("click", addComment);
$("commentLoginBtn").addEventListener("click", () => openAuth("login", "Please log in to comment."));

$("searchInput").addEventListener("input", (event) => {
    searchTerm = event.target.value;
    renderHome();
});

$("blogContent").addEventListener("input", () => {
    $("charCount").textContent = `${$("blogContent").value.length} characters`;
});

$("loginBtn").addEventListener("click", () => openAuth("login"));
$("registerBtn").addEventListener("click", () => openAuth("register"));
$("rcloseAuthBtn").addEventListener("click", closeAuth);
$("lcloseAuthBtn").addEventListener("click", closeAuth);
$("switchToLogin").addEventListener("click", () => openAuth("login"));
$("switchToRegister").addEventListener("click", () => openAuth("register"));

$("registerFormElement").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("authMessage").textContent = "Creating account...";

    try {
        await api("/api/register", "POST", {
            username: $("registerUsername").value.trim(),
            email: $("registerEmail").value.trim(),
            password: $("registerPassword").value
        });
        $("authMessage").textContent = "Account created! You can now log in.";
        event.target.reset();
    } catch (error) {
        $("authMessage").textContent = error.message;
    }
});

$("loginFormElement").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("authMessage").textContent = "Logging in...";

    try {
        await api("/api/login", "POST", {
            email: $("loginEmail").value.trim(),
            password: $("loginPassword").value
        });
        await loadMe();
        event.target.reset();
        closeAuth();
        await loadFeed();
        showSection("home");
        notify("Welcome, " + me.username + "!");
    } catch (error) {
        $("authMessage").textContent = error.message;
    }
});

$("logoutBtn").addEventListener("click", async () => {
    const ok = await askModal({
        title: "Log out?",
        message: "You will need to log in again to write or comment.",
        confirmText: "Log out"
    });

    if (!ok) {
        return;
    }

    try {
        await api("/api/logout", "POST");
    } catch (error) {
        notify(error.message, true);
        return;
    }

    setUser(null);
    await loadFeed();
    showSection("home");
});

$("passwordForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    if ($("pwNew").value !== $("pwConfirm").value) {
        notify("New passwords do not match.", true);
        return;
    }

    try {
        await api("/api/account/password", "POST", {
            currentPassword: $("pwCurrent").value,
            newPassword: $("pwNew").value
        });
        event.target.reset();
        notify("Password changed.");
    } catch (error) {
        notify(error.message, true);
    }
});

$("deleteAccountBtn").addEventListener("click", async () => {
    const values = await askModal({
        title: "Delete your account?",
        message: "This permanently deletes your account, your blogs and your comments.",
        fields: [{ id: "pw", label: "Confirm your password", type: "password" }],
        confirmText: "Delete account",
        danger: true
    });

    if (!values) {
        return;
    }

    try {
        await api("/api/account", "DELETE", { password: values.pw });
        setUser(null);
        await loadFeed();
        showSection("home");
        notify("Account deleted.");
    } catch (error) {
        notify(error.message, true);
    }
});

async function init() {
    await loadMe();
    const ok = await loadFeed();
    showSection("home");

    if (!ok) {
        setTimeout(init, 4000);
    }
}

init();


/* profile-edit */
(function () {
    const nameInput = $("accUsername");
    const emailInput = $("accEmail");

    nameInput.readOnly = false;
    emailInput.readOnly = false;
    nameInput.maxLength = 30;
    nameInput.autocomplete = "off";
    emailInput.autocomplete = "off";

    nameInput.parentElement.insertAdjacentHTML("beforeend", '<small class="field-hint" id="hintUsername"></small>');
    emailInput.parentElement.insertAdjacentHTML("beforeend", '<small class="field-hint" id="hintEmail"></small>');
    emailInput.parentElement.insertAdjacentHTML("afterend", '<button type="button" class="primary-btn" id="saveProfileBtn">Save changes</button>');

    const bad = { username: false, email: false };
    let timer = null;

    function setHint(id, message, ok) {
        const el = $(id);
        el.textContent = message || "";
        el.className = "field-hint" + (message ? (ok ? " ok" : " bad") : "");
    }

    async function runCheck() {
        if (!me) return;

        const params = new URLSearchParams();
        const name = nameInput.value.trim();
        const email = emailInput.value.trim();
        const nameChanged = name !== me.username;
        const emailChanged = !me.is_admin && email.toLowerCase() !== me.email.toLowerCase();

        if (nameChanged) params.set("username", name);
        if (emailChanged) params.set("email", email);

        bad.username = false;
        bad.email = false;
        if (!nameChanged) setHint("hintUsername", "", true);
        if (!emailChanged) setHint("hintEmail", me.is_admin ? "The admin email cannot be changed." : "", true);

        if (!nameChanged && !emailChanged) {
            $("saveProfileBtn").disabled = false;
            return;
        }

        try {
            const result = await api("/api/check?" + params.toString());

            if (result.username) {
                bad.username = !result.username.ok;
                setHint("hintUsername", result.username.message, result.username.ok);
            }

            if (result.email) {
                bad.email = !result.email.ok;
                setHint("hintEmail", result.email.message, result.email.ok);
            }
        } catch (_) {
            // Server will validate on save.
        }

        $("saveProfileBtn").disabled = bad.username || bad.email;
    }

    function schedule() {
        clearTimeout(timer);
        timer = setTimeout(runCheck, 400);
    }

    nameInput.addEventListener("input", schedule);
    emailInput.addEventListener("input", schedule);

    const baseRenderAccount = renderAccount;
    renderAccount = function () {
        baseRenderAccount();
        nameInput.value = me.username;
        emailInput.value = me.email;
        emailInput.disabled = Boolean(me.is_admin);
        bad.username = false;
        bad.email = false;
        $("saveProfileBtn").disabled = false;
        setHint("hintUsername", "", true);
        setHint("hintEmail", me.is_admin ? "The admin email cannot be changed." : "", true);
    };

    $("saveProfileBtn").addEventListener("click", async () => {
        const body = {};
        const name = nameInput.value.trim();
        const email = emailInput.value.trim();

        if (name !== me.username) body.username = name;
        if (!me.is_admin && email.toLowerCase() !== me.email.toLowerCase()) body.email = email;

        if (!Object.keys(body).length) {
            notify("Nothing to change.");
            return;
        }

        if (body.email) {
            const values = await askModal({
                title: "Confirm your password",
                message: "Enter your password to change your email.",
                fields: [{ id: "pw", label: "Password", type: "password" }],
                confirmText: "Confirm"
            });

            if (!values) return;
            body.password = values.pw;
        }

        try {
            await api("/api/account/profile", "POST", body);
            await loadMe();
            await loadFeed();
            renderAccount();
            notify("Profile updated.");
        } catch (error) {
            notify(error.message, true);
        }
    });
})();


/* del-comment */
document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delcomment]");
    if (!button) return;

    const blog = feed.find((item) => item.id === currentBlogId);
    const id = Number(button.dataset.delcomment);
    if (!blog) return;

    const ok = await askModal({
        title: "Delete comment?",
        message: "This cannot be undone.",
        confirmText: "Delete",
        danger: true
    });
    if (!ok) return;

    try {
        await api(`/api/comments/${id}`, "DELETE");
        blog.comments = blog.comments.filter((comment) => comment.id !== id);
        blog.comment_count = Math.max(0, blog.comment_count - 1);
        displayComments(blog);
        notify("Comment deleted.");
    } catch (error) {
        notify(error.message, true);
    }
});
