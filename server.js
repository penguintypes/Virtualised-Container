
const express = require("express");
const mysql = require("mysql2/promise");
const bcrypt = require("bcrypt");
const session = require("express-session");
const dotenv = require("dotenv");
const path = require("path");

dotenv.config();

const app = express();

// Read JSON data sent by the frontend.
app.use(express.json());

// Serve the existing BlogDrop website.
app.use(express.static(path.join(__dirname, "..")));

// Configure login sessions.
app.use(
    session({
        secret: process.env.SESSION_SECRET,
        resave: false,
        saveUninitialized: false,
        cookie: {
            httpOnly: true,
            sameSite: "lax",
            secure: false,
            maxAge: 24 * 60 * 60 * 1000
        }
    })
);

// Connect Node.js to MySQL.
const db = mysql.createPool({
    host: process.env.DB_HOST,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME
});

// Test the database connection.
app.get("/api/health", async (req, res) => {
    try {
        await db.query("SELECT 1");
        res.json({
            message: "BlogDrop database connected successfully!"
        });
    } catch (error) {
        console.error(error.message);
        res.status(500).json({
            message: "Database connection failed."
        });
    }
});

// Register a new user.
app.post("/api/register", async (req, res) => {
    try {
        const { username, email, password } = req.body;

        // Check that all fields are provided.
        if (
            typeof username !== "string" ||
            typeof email !== "string" ||
            typeof password !== "string"
        ) {
            return res.status(400).json({
                message: "Please provide a username, email and password."
            });
        }

        const cleanUsername = username.trim();
        const cleanEmail = email.trim().toLowerCase();

        if (
            cleanUsername.length < 2 ||
            cleanUsername.length > 50
        ) {
            return res.status(400).json({
                message: "Username must be 2–50 characters long."
            });
        }

        if (
            cleanEmail.length > 255 ||
            !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)
        ) {
            return res.status(400).json({
                message: "Please enter a valid email address."
            });
        }

        if (password.length < 8 || password.length > 72) {
            return res.status(400).json({
                message: "Password must be 8–72 characters long."
            });
        }

        // Check whether this email is already registered.
        const [existingUsers] = await db.execute(
            "SELECT id FROM users WHERE email = ?",
            [cleanEmail]
        );

        if (existingUsers.length > 0) {
            return res.status(409).json({
                message: "This email is already registered."
            });
        }

        // Hash the password before storing it.
        const passwordHash = await bcrypt.hash(password, 12);

        // Insert the new account into MySQL.
        const [result] = await db.execute(
            `INSERT INTO users
             (username, email, password_hash)
             VALUES (?, ?, ?)`,
            [cleanUsername, cleanEmail, passwordHash]
        );

        res.status(201).json({
            message: "Registration successful!",
            user: {
                id: result.insertId,
                username: cleanUsername,
                email: cleanEmail
            }
        });

    } catch (error) {
        if (error.code === "ER_DUP_ENTRY") {
            return res.status(409).json({
                message: "This email is already registered."
            });
        }

        console.error("Registration error:", error.message);

        res.status(500).json({
            message: "Registration failed. Please try again."
        });
    }
});

 // Log in an existing user.
 console.log("Registering POST /api/login");
app.post("/api/login", async (req, res) => {
    try {
        const { email, password } = req.body;

        if (
            typeof email !== "string" ||
            typeof password !== "string" ||
            email.length > 255 ||
            password.length > 72
        ) {
            return res.status(400).json({
                message: "Please enter a valid email and password."
            });
        }

        // Find the account by email.
        const [users] = await db.execute(
            "SELECT id, username, email, password_hash FROM users WHERE email = ?",
            [email.trim().toLowerCase()]
        );

        if (users.length === 0) {
            return res.status(401).json({
                message: "Invalid email or password."
            });
        }

        const user = users[0];

        // Compare the submitted password with its stored hash.
        const passwordMatches = await bcrypt.compare(
            password,
            user.password_hash
        );

        if (!passwordMatches) {
            return res.status(401).json({
                message: "Invalid email or password."
            });
        }

        // Create a fresh session after successful login.
        req.session.regenerate((error) => {
            if (error) {
                return res.status(500).json({
                    message: "Could not create login session."
                });
            }

            req.session.userId = user.id;

            req.session.save((error) => {
                if (error) {
                    return res.status(500).json({
                        message: "Could not save login session."
                    });
                }

                res.json({
                    message: "Login successful!",
                    user: {
                        id: user.id,
                        username: user.username,
                        email: user.email
                    }
                });
            });
        });

    } catch (error) {
        console.error("Login error:", error.message);

        res.status(500).json({
            message: "Login failed. Please try again."
        });
    }
});

// Check which user is currently logged in.
app.get("/api/me", async (req, res) => {
    if (!req.session.userId) {
        return res.status(401).json({
            message: "You are not logged in."
        });
    }

    try {
        const [users] = await db.execute(
            "SELECT id, username, email FROM users WHERE id = ?",
            [req.session.userId]
        );

        if (users.length === 0) {
            return res.status(401).json({
                message: "User account not found."
            });
        }

        res.json({ user: users[0] });
    } catch (error) {
        console.error("Session check error:", error.message);

        res.status(500).json({
            message: "Could not check login status."
        });
    }
});

/* Get blogs belonging to the logged-in user. */
app.get("/api/blogs", async (req, res) => {
    // Require a logged-in session.
    if (!req.session.userId) {
        return res.status(401).json({
            message: "Please log in to view your blogs."
        });
    }

    try {
        
        // Retrieve blogs with their actual comment counts.
        const [blogs] = await db.execute(
            `SELECT
                b.id,
                b.user_id,
                b.title,
                b.content,
                b.views,
                b.created_at,
                (
                    SELECT COUNT(*)
                    FROM comments c
                    WHERE c.blog_id = b.id
                ) AS comment_count
             FROM blogs b
             WHERE b.user_id = ?
             ORDER BY b.created_at DESC`,
            [req.session.userId]
        );

        res.json({ blogs });

    } catch (error) {
        console.error("Fetch blogs error:", error.message);
        res.status(500).json({
            message: "Could not load blogs."
        });
    }
});

/* Create a blog for the logged-in user. */
app.post("/api/blogs", async (req, res) => {
    // Require a logged-in session.
    if (!req.session.userId) {
        return res.status(401).json({
            message: "Please log in to publish a blog."
        });
    }

    try {
        const { title, content } = req.body;

        // Validate the blog fields.
        if (
            typeof title !== "string" ||
            typeof content !== "string" ||
            !title.trim() ||
            !content.trim() ||
            title.trim().length > 100
        ) {
            return res.status(400).json({
                message: "Enter a title (up to 100 characters) and blog content."
            });
        }

        // The owner comes from the verified session, not the request body.
        const [result] = await db.execute(
            `INSERT INTO blogs (user_id, title, content)
             VALUES (?, ?, ?)`,
            [
                req.session.userId,
                title.trim(),
                content.trim()
            ]
        );

        res.status(201).json({
            message: "Blog published successfully.",
            blog: {
                id: result.insertId,
                user_id: req.session.userId,
                title: title.trim(),
                content: content.trim(),
                views: 0
            }
        });
    } catch (error) {
        console.error("Create blog error:", error.message);
        res.status(500).json({
            message: "Could not publish blog."
        });
    }
});


/* Get comments for a blog owned by the logged-in user. */
app.get("/api/blogs/:id/comments", async (req, res) => {
    if (!req.session.userId) {
        return res.status(401).json({
            message: "Please log in to view comments."
        });
    }

    try {
        const blogId = Number(req.params.id);

        if (!Number.isInteger(blogId) || blogId <= 0) {
            return res.status(400).json({
                message: "Invalid blog ID."
            });
        }

        // Confirm the blog belongs to this user.
        const [blogsFound] = await db.execute(
            "SELECT id FROM blogs WHERE id = ? AND user_id = ?",
            [blogId, req.session.userId]
        );

        if (blogsFound.length === 0) {
            return res.status(404).json({
                message: "Blog not found."
            });
        }

        const [comments] = await db.execute(
            `SELECT id, name, content, created_at
             FROM comments
             WHERE blog_id = ?
             ORDER BY created_at ASC`,
            [blogId]
        );

        res.json({ comments });
    } catch (error) {
        console.error("Fetch comments error:", error.message);
        res.status(500).json({
            message: "Could not load comments."
        });
    }
});


/* Save a comment for a blog owned by the logged-in user. */
app.post("/api/blogs/:id/comments", async (req, res) => {
    if (!req.session.userId) {
        return res.status(401).json({
            message: "Please log in to comment."
        });
    }

    try {
        const blogId = Number(req.params.id);
        const { name, text } = req.body;

        if (!Number.isInteger(blogId) || blogId <= 0) {
            return res.status(400).json({
                message: "Invalid blog ID."
            });
        }

        if (
            typeof name !== "string" ||
            typeof text !== "string" ||
            !name.trim() ||
            !text.trim() ||
            name.trim().length > 100 ||
            text.trim().length > 5000
        ) {
            return res.status(400).json({
                message: "Enter a name (up to 100 characters) and a comment (up to 5000 characters)."
            });
        }

        // Allow comments only on the user's own blogs for now.
        const [blogsFound] = await db.execute(
            "SELECT id FROM blogs WHERE id = ? AND user_id = ?",
            [blogId, req.session.userId]
        );

        if (blogsFound.length === 0) {
            return res.status(404).json({
                message: "Blog not found."
            });
        }

        const [result] = await db.execute(
            `INSERT INTO comments (blog_id, user_id, name, content)
             VALUES (?, ?, ?, ?)`,
            [blogId, req.session.userId, name.trim(), text.trim()]
        );

        res.status(201).json({
            message: "Comment saved successfully.",
            comment: {
                id: result.insertId,
                name: name.trim(),
                text: text.trim(),
                date: new Date().toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                    year: "numeric"
                })
            }
        });
    } catch (error) {
        console.error("Save comment error:", error.message);
        res.status(500).json({
            message: "Could not save comment."
        });
    }
});




/* Delete a blog belonging to the logged-in user. */
app.delete("/api/blogs/:id", async (req, res) => {
    // Require a logged-in session.
    if (!req.session.userId) {
        return res.status(401).json({
            message: "Please log in to delete a blog."
        });
    }

    try {
        // Validate the blog ID.
        const blogId = Number(req.params.id);

        if (!Number.isInteger(blogId) || blogId <= 0) {
            return res.status(400).json({
                message: "Invalid blog ID."
            });
        }

        // Delete only a blog owned by the logged-in user.
        const [result] = await db.execute(
            "DELETE FROM blogs WHERE id = ? AND user_id = ?",
            [blogId, req.session.userId]
        );

        if (result.affectedRows === 0) {
            return res.status(404).json({
                message: "Blog not found or you do not have permission to delete it."
            });
        }

        res.json({
            message: "Blog deleted successfully."
        });

    } catch (error) {
        console.error("Delete blog error:", error.message);

        res.status(500).json({
            message: "Could not delete blog."
        });
    }
});


/* Increment the view count for a blog owned by the logged-in user. */
app.post("/api/blogs/:id/view", async (req, res) => {
    // Require a logged-in session.
    if (!req.session.userId) {
        return res.status(401).json({
            message: "Please log in to update blog views."
        });
    }

    try {
        // Validate the blog ID.
        const blogId = Number(req.params.id);

        if (!Number.isInteger(blogId) || blogId <= 0) {
            return res.status(400).json({
                message: "Invalid blog ID."
            });
        }

        // Increment views only for a blog owned by this user.
        const [result] = await db.execute(
            "UPDATE blogs SET views = views + 1 WHERE id = ? AND user_id = ?",
            [blogId, req.session.userId]
        );

        if (result.affectedRows === 0) {
            return res.status(404).json({
                message: "Blog not found or you do not have permission to update its views."
            });
        }

        // Get the updated view count.
        const [rows] = await db.execute(
            "SELECT views FROM blogs WHERE id = ? AND user_id = ?",
            [blogId, req.session.userId]
        );

        res.json({
            message: "Blog view updated.",
            views: rows[0].views
        });

    } catch (error) {
        console.error("Update blog views error:", error.message);
        res.status(500).json({
            message: "Could not update blog views."
        });
    }
});



// Log out the current user.
app.post("/api/logout", (req, res) => {
    req.session.destroy((error) => {
        if (error) {
            return res.status(500).json({
                message: "Logout failed."
            });
        }

        res.clearCookie("connect.sid", {
            httpOnly: true,
            sameSite: "lax",
            secure: false,
            path: "/"
        });

        res.json({
            message: "Logged out successfully."
        });
    });
});

// Start the server only if MySQL is reachable.
async function startServer() {
    try {
        await db.query("SELECT 1");

        app.listen(process.env.PORT || 3000, () => {
            console.log(
                "BlogDrop server running at http://localhost:3000"
            );
        });
    } catch (error) {
        console.error(
            "MySQL connection failed:",
            error.message
        );
        process.exit(1);
    }
}

startServer();
