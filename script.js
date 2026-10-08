let blogs = JSON.parse(
    localStorage.getItem("blogDropBlogs")
) || [];

let currentBlogId = null;

function saveBlogs() {

    localStorage.setItem(
        "blogDropBlogs",
        JSON.stringify(blogs)
    );

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

function publishBlog() {

    const title =
        document
            .getElementById("blogTitle")
            .value
            .trim();

    const content =
        document
            .getElementById("blogContent")
            .value
            .trim();

    if (!title) {

        alert("Please enter a blog title.");

        return;

    }


    if (!content) {

        alert("Please write something in your blog.");

        return;

    }

    const newBlog = {

        id: Date.now(),

        title: title,

        content: content,

        date: new Date().toLocaleDateString(
            "en-IN",
            {
                day: "numeric",
                month: "short",
                year: "numeric"
            }
        ),

        views: 0,

        comments: []

    };

    blogs.unshift(newBlog);

    saveBlogs();

    document
        .getElementById("blogTitle")
        .value = "";

    document
        .getElementById("blogContent")
        .value = "";

    charCount.textContent =
        "0 characters";

    updateDashboard();
    displayBlogs();


    alert("Blog published successfully!");


    showSection("blogs");

}

function updateDashboard() {

    document
        .getElementById("totalBlogs")
        .textContent =
        blogs.length;

    const totalViews =
        blogs.reduce(
            (total, blog) =>
                total + blog.views,
            0
        );

    document
        .getElementById("totalViews")
        .textContent =
        totalViews;

    const totalComments =
        blogs.reduce(
            (total, blog) =>
                total + blog.comments.length,
            0
        );

    document
        .getElementById("totalComments")
        .textContent =
        totalComments;

    const recentBlogs =
        document.getElementById("recentBlogs");


    if (blogs.length === 0) {

        recentBlogs.innerHTML = `

            <div class="empty-state">

                <div>📝</div>

                <h3>No blogs yet</h3>

                <p>
                    Start writing your first blog.
                </p>

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

    recentBlogs.innerHTML =
        blogs.slice(0, 5)
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
                    💬 ${blog.comments.length}
                </span>

            </div>

        </div>

    `;

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
                                💬 ${blog.comments.length} comments
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

function openBlog(id) {

    const blog =
        blogs.find(blog => blog.id === id);


    if (!blog) {
        return;
    }

    blog.views++;

    saveBlogs();


    currentBlogId = id;

    document
        .getElementById("readerTitle")
        .textContent =
        blog.title;


    document
        .getElementById("readerContent")
        .textContent =
        blog.content;


    document
        .getElementById("readerDate")
        .textContent =
        blog.date;


    document
        .getElementById("readerViews")
        .textContent =
        `${blog.views} views`;

    displayComments(blog);

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

function addComment() {

    if (!currentBlogId) {
        return;
    }


    const name =
        document
            .getElementById("commentName")
            .value
            .trim();

    const text =
        document
            .getElementById("commentText")
            .value
            .trim();

    if (!name) {

        alert("Please enter your name.");

        return;

    }


    if (!text) {

        alert("Please write a comment.");

        return;

    }

    const blog =
        blogs.find(
            blog => blog.id === currentBlogId
        );


    if (!blog) {
        return;
    }

    const comment = {

        id: Date.now(),

        name: name,

        text: text,

        date: new Date().toLocaleDateString(
            "en-IN",
            {
                day: "numeric",
                month: "short",
                year: "numeric"
            }
        )

    };

    blog.comments.push(comment);

    saveBlogs();

    document
        .getElementById("commentName")
        .value = "";

    document
        .getElementById("commentText")
        .value = "";


    /*
        Refresh comments
    */

    displayComments(blog);

    updateDashboard();

}

function deleteBlog(id) {

    const confirmDelete =
        confirm(
            "Are you sure you want to delete this blog?"
        );


    if (!confirmDelete) {
        return;
    }


    blogs =
        blogs.filter(
            blog => blog.id !== id
        );


    saveBlogs();


    updateDashboard();

    displayBlogs();

}

function escapeHTML(text) {

    const div =
        document.createElement("div");

    div.textContent = text;

    return div.innerHTML;

}

updateDashboard();
displayBlogs();