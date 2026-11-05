
let blogs = [];

let currentBlogId = null;

// Remove the old shared demo blogs.
localStorage.removeItem("blogDropBlogs");

// Guest blogs stay in memory only.
function saveBlogs() {
    // No browser storage for temporary blogs.
}


const navButtons =
    document.querySelectorAll(".nav-btn");

navButtons.forEach(button => {

    button.addEventListener("click", () => {

        const section =
            button.getAttribute("data-section");

        showSection(section);

    });

});


function showSection(sectionId) {
    document
        .querySelectorAll(".page")
        .forEach(page => {

            page.classList.remove("active");

        });

    const section =
        document.getElementById(sectionId);

    if (section) {
        section.classList.add("active");
    }

    navButtons.forEach(button => {

        button.classList.remove("active");

        if (
            button.dataset.section === sectionId
        ) {
            button.classList.add("active");
        }

    });

    updateDashboard();
    displayBlogs();

    document
        .getElementById("sidebar")
        .classList.remove("open");

}

document
    .getElementById("menuBtn")
    .addEventListener("click", () => {

        document
            .getElementById("sidebar")
            .classList.toggle("open");

    });

const blogContent =
    document.getElementById("blogContent");

const charCount =
    document.getElementById("charCount");


blogContent.addEventListener("input", () => {

    const count =
        blogContent.value.length;

    charCount.textContent =
        `${count} characters`;

});


async function publishBlog() {
    // Get the blog title and content.
    const title = document
        .getElementById("blogTitle")
        .value
        .trim();

    const content = document
        .getElementById("blogContent")
        .value
        .trim();

    // Validate the title.
    if (!title) {
        alert("Please enter a blog title.");
        return;
    }

    // Validate the content.
    if (!content) {
        alert("Please write something in your blog.");
        return;
    }

    // Check whether a user is logged in.
    let loggedIn = false;

    try {
        const sessionResponse = await fetch("/api/me");

        loggedIn = sessionResponse.ok;
    } catch (error) {
        alert("Cannot connect to the server. Please try again.");
        return;
    }

    // Logged-in users save their blogs in MySQL.
    if (loggedIn) {
        try {
            const response = await fetch("/api/blogs", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    title: title,
                    content: content
                })
            });

            const data = await response.json();

            if (!response.ok) {
                alert(data.message || "Could not publish blog.");
                return;
            }

            // Clear the editor after successful publishing.
            document.getElementById("blogTitle").value = "";
            document.getElementById("blogContent").value = "";
            charCount.textContent = "0 characters";

            // Refresh the blog list from the database.
            await loadBlogsFromDatabase();

            updateDashboard();
            displayBlogs();

            alert("Blog published successfully!");
            showSection("blogs");
            return;

        } catch (error) {
            alert("Could not connect to the server. Please try again.");
            console.error("Publish blog error:", error);
            return;
        }
    }

    // Guests can create temporary demo blogs.
    const newBlog = {
        id: Date.now(),
        title: title,
        content: content,
        date: new Date().toLocaleDateString("en-IN", {
            day: "numeric",
            month: "short",
            year: "numeric"
        }),
        views: 0,
        comments: []
    };

    blogs.unshift(newBlog);

    saveBlogs();

    document.getElementById("blogTitle").value = "";
    document.getElementById("blogContent").value = "";
    charCount.textContent = "0 characters";

    updateDashboard();
    displayBlogs();

    alert("Temporary demo blog published!");
    showSection("blogs");
}



async function updateDashboard() {
    // Update total blogs.
    document.getElementById("totalBlogs").textContent =
        blogs.length;

    // Calculate total views.
    const totalViews = blogs.reduce(
        (total, blog) => total + (Number(blog.views) || 0),
        0
    );

    document.getElementById("totalViews").textContent =
        totalViews;

    // Calculate total comments using database counts.
const totalComments = blogs.reduce(
    (total, blog) => total + (blog.commentCount ?? blog.comments?.length ?? 0),
    0
);

    document.getElementById("totalComments").textContent =
        totalComments;

    // Display recent blogs.
    const recentBlogs = document.getElementById("recentBlogs");

    if (blogs.length === 0) {
        recentBlogs.innerHTML = `
            <div class="empty-state">
                <div>📝</div>
                <h3>No blogs yet</h3>
                <p>Start writing your first blog.</p>
                <button
                    class="primary-btn"
                    onclick="showSection('write')"
                >
                    Write Your First Blog
                </button>
            </div>
        `;
        return;
    }

    recentBlogs.innerHTML = blogs
        .slice(0, 5)
        .map(blog => createBlogItem(blog))
        .join("");
}


function createBlogItem(blog) {

    return `

        <div
            class="blog-item"
            onclick="openBlog(${blog.id})"
        >

            <h3>
                ${escapeHTML(blog.title)}
            </h3>

            <p>
                ${escapeHTML(
                    blog.content.substring(0, 120)
                )}...
            </p>

            <div class="blog-info">

                <span>
                    📅 ${blog.date}
                </span>

                <span>
                    👁️ ${blog.views}
                </span>

                <span>
                    💬 ${blog.commentCount ?? blog.comments.length}
                </span>

            </div>

        </div>

    `;

}


async function loadBlogsFromDatabase() {
    try {
        // Request blogs belonging to the logged-in user.
        const response = await fetch("/api/blogs");

        // If the user is not logged in, don't load database blogs.
        if (response.status === 401) {
            return;
        }

        const data = await response.json();

        if (!response.ok) {
            alert(data.message || "Could not load your blogs.");
            return;
        }

        // Convert database records to the format your UI expects.
        blogs = data.blogs.map(blog => ({
            id: blog.id,
            title: blog.title,
            content: blog.content,
            date: new Date(blog.created_at).toLocaleDateString(
                "en-IN",
                {
                    day: "numeric",
                    month: "short",
                    year: "numeric"
                }
            ),
                        views: blog.views,
            commentCount: Number(blog.comment_count) || 0,
            comments: []
        }));

    } catch (error) {
        console.error("Load blogs error:", error);
        alert("Could not connect to the server to load blogs.");
    }
}

function displayBlogs() {

    const container =
        document.getElementById("allBlogs");


    if (blogs.length === 0) {

        container.innerHTML = `

            <div class="empty-state">

                <div>📚</div>

                <h3>No published blogs</h3>

                <p>
                    Your published blogs will appear here.
                </p>

            </div>

        `;

        return;

    }

    container.innerHTML =
        blogs
            .map(blog => {

                return `

                    <div class="my-blog-card">

                        <h2>
                            ${escapeHTML(blog.title)}
                        </h2>

                        <p class="blog-preview">
                            ${escapeHTML(
                                blog.content.substring(
                                    0,
                                    160
                                )
                            )}...
                        </p>

                        <div class="blog-card-stats">

                            <span>
                                👁️ ${blog.views} views
                            </span>

                            <span>
                                💬 ${blog.commentCount ?? blog.comments.length} comments
                            </span>

                            <span>
                                📅 ${blog.date}
                            </span>

                        </div>


                        <div class="blog-card-buttons">

                            <button
                                class="read-btn"
                                onclick="openBlog(${blog.id})"
                            >
                                Read Blog
                            </button>

                            <button
                                class="delete-btn"
                                onclick="deleteBlog(${blog.id})"
                            >
                                Delete
                            </button>

                        </div>

                    </div>

                `;

            })
            .join("");

}



async function openBlog(id) {
    // Find the selected blog.
    let blog = blogs.find(blog => blog.id === id);

    if (!blog) {
        return;
    }

    try {
        // Check whether the user is logged in.
        const sessionResponse = await fetch("/api/me");

        if (sessionResponse.ok) {
            // Increment the view count in MySQL.
            const viewResponse = await fetch(`/api/blogs/${id}/view`, {
                method: "POST"
            });

            const viewData = await viewResponse.json();

            if (!viewResponse.ok) {
                alert(viewData.message || "Could not update blog views.");
                return;
            }

            // Update the view count.
            blog.views = viewData.views;

            // Load the user's latest blogs from MySQL.
            await loadBlogsFromDatabase();

            // Find the blog again after reloading.
            blog = blogs.find(blog => blog.id === id);

            if (!blog) {
                return;
            }

            // Load saved comments from MySQL.
            const commentsResponse = await fetch(
                `/api/blogs/${id}/comments`
            );

            const commentsData = await commentsResponse.json();

            if (!commentsResponse.ok) {
                alert(commentsData.message || "Could not load comments.");
                return;
            }

            // Convert database comments to the UI format.
            blog.comments = commentsData.comments.map(comment => ({
                id: comment.id,
                name: comment.name,
                text: comment.content,
                date: new Date(comment.created_at).toLocaleDateString(
                    "en-IN",
                    {
                        day: "numeric",
                        month: "short",
                        year: "numeric"
                    }
                )
            }));
        } else {
            // Guest demo blogs update views only in memory.
            blog.views++;
        }
    } catch (error) {
        console.error("Open blog error:", error);
        alert("Could not connect to the server. Please try again.");
        return;
    }

    // Remember which blog is open.
    currentBlogId = id;

    // Display the blog details.
    document.getElementById("readerTitle").textContent = blog.title;
    document.getElementById("readerContent").textContent = blog.content;
    document.getElementById("readerDate").textContent = blog.date;
    document.getElementById("readerViews").textContent =
        `${blog.views} views`;

    // Display the saved comments.
    displayComments(blog);

    // Open the reader page.
    showSection("reader");
}


function displayComments(blog) {

    const commentsList =
        document.getElementById("commentsList");


    document
        .getElementById("commentCount")
        .textContent =
        blog.comments.length;


    if (blog.comments.length === 0) {

        commentsList.innerHTML = `

            <div class="empty-state">

                <p>
                    No comments yet. Be the first!
                </p>

            </div>

        `;

        return;

    }


    commentsList.innerHTML =
        blog.comments
            .map(comment => {

                return `

                    <div class="comment">

                        <div class="comment-header">

                            <span class="comment-name">
                                ${escapeHTML(
                                    comment.name
                                )}
                            </span>

                            <span class="comment-date">
                                ${comment.date}
                            </span>

                        </div>

                        <p>
                            ${escapeHTML(
                                comment.text
                            )}
                        </p>

                    </div>

                `;

            })
            .join("");

}


async function addComment() {
    // Make sure a blog is open.
    if (!currentBlogId) {
        return;
    }

    // Get the name and comment text.
    const name = document.getElementById("commentName").value.trim();
    const text = document.getElementById("commentText").value.trim();

    // Validate the fields.
    if (!name) {
        alert("Please enter your name.");
        return;
    }

    if (!text) {
        alert("Please write a comment.");
        return;
    }

    // Find the currently open blog.
    const blog = blogs.find(blog => blog.id === currentBlogId);

    if (!blog) {
        return;
    }

    try {
        // Check whether the user is logged in.
        const sessionResponse = await fetch("/api/me");

        if (!sessionResponse.ok) {
            alert("Please log in to save comments.");
            return;
        }

        // Save the comment in MySQL.
        const response = await fetch(
            `/api/blogs/${currentBlogId}/comments`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ name, text })
            }
        );

        const data = await response.json();

        if (!response.ok) {
            alert(data.message || "Could not save comment.");
            return;
        }

        // Add the saved comment to the current blog.
blog.comments.push(data.comment);

// Increase this blog's comment count immediately.
blog.commentCount = (Number(blog.commentCount) || 0) + 1;

        // Clear the input fields.
        document.getElementById("commentName").value = "";
        document.getElementById("commentText").value = "";

        // Refresh the comment list and dashboard.
        displayComments(blog);
        updateDashboard();
        displayBlogs();

    } catch (error) {
        console.error("Save comment error:", error);
        alert("Could not connect to the server. Please try again.");
    }
}



async function deleteBlog(id) {
    // Ask for confirmation before deleting.
    const confirmDelete = confirm(
        "Are you sure you want to delete this blog?"
    );

    if (!confirmDelete) {
        return;
    }

    // Check whether a user is logged in.
    try {
        const sessionResponse = await fetch("/api/me");

        if (sessionResponse.ok) {
            // Delete the blog from MySQL.
            const response = await fetch(`/api/blogs/${id}`, {
                method: "DELETE"
            });

            const data = await response.json();

            if (!response.ok) {
                alert(data.message || "Could not delete blog.");
                return;
            }

            alert("Blog deleted successfully!");

            // Reload this user's blogs from MySQL.
            await loadBlogsFromDatabase();

        } else {
            // Guests can delete only temporary demo blogs.
            blogs = blogs.filter(blog => blog.id !== id);
        }

        // Refresh the displayed information.
        if (currentBlogId === id) {
            currentBlogId = null;
            showSection("blogs");
        }

        updateDashboard();
        displayBlogs();

    } catch (error) {
        console.error("Delete blog error:", error);
        alert("Could not connect to the server. Please try again.");
    }
}


function escapeHTML(text) {

    const div =
        document.createElement("div");

    div.textContent = text;

    return div.innerHTML;

}

updateDashboard();
displayBlogs();


const authForms = document.getElementById("authForms");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const authMessage = document.getElementById("authMessage");

// Open the registration form.
document.getElementById("registerBtn").addEventListener("click", () => {
    document.body.classList.add("auth-open");
    authForms.hidden = false;
    loginForm.hidden = true;
    registerForm.hidden = false;
    authMessage.textContent = "";
    authForms.scrollIntoView({ behavior: "smooth" });
});

// Open the login form.
document.getElementById("loginBtn").addEventListener("click", () => {
    document.body.classList.add("auth-open");
    authForms.hidden = false;
    registerForm.hidden = true;
    loginForm.hidden = false;
    authMessage.textContent = "";
    authForms.scrollIntoView({ behavior: "smooth" });
});

// Close the forms.

document.getElementById("rcloseAuthBtn").addEventListener("click", () => {
    authForms.hidden = true;
    document.body.classList.remove("auth-open");
});

document.getElementById("lcloseAuthBtn").addEventListener("click", () => {
    authForms.hidden = true;
    document.body.classList.remove("auth-open");
});

// Register a new user.
document.getElementById("registerFormElement").addEventListener("submit", async (event) => {
    event.preventDefault();

    const username = document.getElementById("registerUsername").value.trim();
    const email = document.getElementById("registerEmail").value.trim();
    const password = document.getElementById("registerPassword").value;

    authMessage.textContent = "Creating account...";

    try {
        const response = await fetch("/api/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, email, password })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.message || "Registration failed.");
        }

        authMessage.textContent = "Account created! You can now log in.";
        document.getElementById("registerFormElement").reset();

    } catch (error) {
        authMessage.textContent = error.message;
    }
});

// Log in an existing user.
document.getElementById("loginFormElement").addEventListener("submit", async (event) => {
    event.preventDefault();

    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value;

    authMessage.textContent = "Logging in...";

    try {
        const response = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.message || "Login failed.");
        }

        
authMessage.textContent =
    "Welcome, " + data.user.username + "! Login successful.";

// Show the dashboard after successful login.
document.body.classList.remove("guest-mode");

// Load this user's blogs from MySQL.
blogs = [];
await loadBlogsFromDatabase();

updateDashboard();
displayBlogs();
showSection("dashboard");

document.getElementById("authStatus").textContent =
    "Logged in as " + data.user.username;



        document.getElementById("loginBtn").hidden = true;
        document.getElementById("registerBtn").hidden = true;
        document.getElementById("logoutBtn").hidden = false;

        authForms.hidden = true;
        document.body.classList.remove("auth-open");
document.getElementById("authForms").classList.remove("active");


    } catch (error) {
        authMessage.textContent = error.message;
    }
});

// Log out.
document.getElementById("logoutBtn").addEventListener("click", async () => {
    try {
        const response = await fetch("/api/logout", {
            method: "POST"
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.message || "Logout failed.");
        }

        document.getElementById("authStatus").textContent =
            "You are browsing as a guest";
            document.body.classList.add("guest-mode");
            // Clear the previous user's blogs.
blogs = [];
currentBlogId = null;

updateDashboard();
displayBlogs();
showSection("dashboard");
           

        document.getElementById("loginBtn").hidden = false;
        document.getElementById("registerBtn").hidden = false;
        document.getElementById("logoutBtn").hidden = true;

        

    } catch (error) {
        alert(error.message);
    }
});



/* Restore login status after a page refresh. */
async function restoreLoginSession() {
    try {
        const response = await fetch("/api/me");

        if (!response.ok) {
    document.body.classList.add("guest-mode");

    document.getElementById("authStatus").textContent =
        "You are browsing as a guest";

    document.getElementById("loginBtn").hidden = false;
    document.getElementById("registerBtn").hidden = false;
    document.getElementById("logoutBtn").hidden = true;

    return;
}

     const data = await response.json();

// A valid session means the user is logged in.
document.body.classList.remove("guest-mode");

// Load this user's blogs from MySQL.
blogs = [];
await loadBlogsFromDatabase();
updateDashboard();
displayBlogs();
showSection("dashboard");
       

        document.getElementById("authStatus").textContent =
            "Logged in as " + data.user.username;

        document.getElementById("loginBtn").hidden = true;
        document.getElementById("registerBtn").hidden = true;
        document.getElementById("logoutBtn").hidden = false;

    } catch (error) {
        console.error("Could not restore login session:", error);
    }
}


/* Check the session when BlogDrop loads. */
restoreLoginSession();




