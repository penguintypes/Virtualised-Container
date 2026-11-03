
const express = require("express");
const mysql = require("mysql2/promise");
const bcrypt = require("bcrypt");
const session = require("express-session");
const dotenv = require("dotenv");

dotenv.config();

const app = express();

// Read JSON data sent by the frontend.
app.use(express.json());

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
/* identity-v1 */
let lockTail = Promise.resolve();
function acquireLock() {
    let release;
    const next = new Promise((resolve) => { release = resolve; });
    const prev = lockTail;
    lockTail = prev.then(() => next);
    return prev.then(() => release);
}

const RESERVED_NAMES = new Set([
    "admin", "administrator", "root", "support", "help", "staff", "moderator",
    "mod", "system", "blogdrop", "official", "security", "info", "contact",
    "null", "undefined", "api", "www"
]);

function usernameKey(name) {
    return String(name).normalize("NFKC").trim().toLowerCase();
}

function checkUsernameRules(name) {
    if (typeof name !== "string") return "Enter a username.";
    const n = name.trim();
    if (n.length < 3 || n.length > 30) return "Username must be 3-30 characters.";
    if (!/^[A-Za-z0-9._]+$/.test(n)) return "Use only letters, numbers, dots and underscores.";
    if (n.startsWith(".") || n.endsWith(".") || n.includes("..")) return "Dots can't be first, last or doubled.";
    if (RESERVED_NAMES.has(n.toLowerCase())) return "That username is reserved.";
    return null;
}

function emailKey(email) {
    const e = String(email).normalize("NFKC").trim().toLowerCase();
    const at = e.lastIndexOf("@");
    if (at < 1) return e;
    let local = e.slice(0, at);
    let domain = e.slice(at + 1);
    const plus = local.indexOf("+");
    if (plus > 0) local = local.slice(0, plus);
    if (domain === "gmail.com" || domain === "googlemail.com") {
        local = local.replace(/\./g, "");
        domain = "gmail.com";
    }
    return local + "@" + domain;
}

function checkEmailRules(email) {
    if (typeof email !== "string") return "Enter an email.";
    const e = email.trim();
    if (e.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) return "Enter a valid email.";
    return null;
}

async function findConflicts(fields, excludeId) {
    const [rows] = await db.execute("SELECT id, username, email FROM users");
    const out = {};
    if (fields.username !== undefined) {
        const key = usernameKey(fields.username);
        if (rows.some((r) => r.id !== excludeId && usernameKey(r.username) === key)) {
            out.username = "That username is taken.";
        }
    }
    if (fields.email !== undefined) {
        const key = emailKey(fields.email);
        if (rows.some((r) => r.id !== excludeId && emailKey(r.email) === key)) {
            out.email = "That email is already in use.";
        }
    }
    return out;
}

app.post("/api/register", async (req, res, next) => {
    const release = await acquireLock();
    res.on("finish", release);
    res.on("close", release);

    try {
        const { username, email } = req.body || {};

        if (typeof username !== "string" || typeof email !== "string") {
            return next();
        }

        const nameError = checkUsernameRules(username);
        if (nameError) return res.status(400).json({ message: nameError });

        const emailError = checkEmailRules(email);
        if (emailError) return res.status(400).json({ message: emailError });

        const conflicts = await findConflicts({ username, email }, 0);
        if (conflicts.username) return res.status(409).json({ message: conflicts.username });
        if (conflicts.email) return res.status(409).json({ message: conflicts.email });

        next();
    } catch (error) {
        console.error("Register precheck error:", error.message);
        res.status(500).json({ message: "Could not create account." });
    }
});

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

        const [takenNames] = await db.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(?)",
            [cleanUsername]
        );

        if (takenNames.length > 0) {
            return res.status(409).json({
                message: "This username is already taken."
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
    try {
        const user = await currentUser(req);

        if (!user) {
            return res.status(401).json({ message: "You are not logged in." });
        }

        res.json({ user });
    } catch (error) {
        console.error("Session check error:", error.message);
        res.status(500).json({ message: "Could not check login status." });
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
    try {
        const blogId = Number(req.params.id);

        if (!Number.isInteger(blogId) || blogId <= 0) {
            return res.status(400).json({ message: "Invalid blog ID." });
        }

        const [comments] = await db.execute(
            `SELECT id, user_id, name, content, created_at
             FROM comments
             WHERE blog_id = ?
             ORDER BY created_at ASC`,
            [blogId]
        );

        res.json({ comments });
    } catch (error) {
        console.error("Fetch comments error:", error.message);
        res.status(500).json({ message: "Could not load comments." });
    }
});


/* Save a comment for a blog owned by the logged-in user. */
app.post("/api/blogs/:id/comments", async (req, res) => {
    try {
        const user = await currentUser(req);

        if (!user) {
            return res.status(401).json({ message: "Please log in to comment." });
        }

        const blogId = Number(req.params.id);
        const text = typeof req.body.text === "string" ? req.body.text.trim() : "";

        if (!Number.isInteger(blogId) || blogId <= 0) {
            return res.status(400).json({ message: "Invalid blog ID." });
        }

        if (!text || text.length > 5000) {
            return res.status(400).json({
                message: "Enter a comment (up to 5000 characters)."
            });
        }

        const [found] = await db.execute("SELECT id FROM blogs WHERE id = ?", [blogId]);

        if (found.length === 0) {
            return res.status(404).json({ message: "Blog not found." });
        }

        const [result] = await db.execute(
            `INSERT INTO comments (blog_id, user_id, name, content)
             VALUES (?, ?, ?, ?)`,
            [blogId, user.id, user.username, text]
        );

        res.status(201).json({
            message: "Comment saved successfully.",
            comment: {
                id: result.insertId,
                name: user.username,
                text: text,
                date: new Date().toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                    year: "numeric"
                })
            }
        });
    } catch (error) {
        console.error("Save comment error:", error.message);
        res.status(500).json({ message: "Could not save comment." });
    }
});




/* Delete a blog belonging to the logged-in user. */
app.delete("/api/blogs/:id", async (req, res) => {
    try {
        const user = await currentUser(req);

        if (!user) {
            return res.status(401).json({ message: "Please log in to delete a blog." });
        }

        const blogId = Number(req.params.id);

        if (!Number.isInteger(blogId) || blogId <= 0) {
            return res.status(400).json({ message: "Invalid blog ID." });
        }

        const [found] = await db.execute("SELECT user_id FROM blogs WHERE id = ?", [blogId]);

        if (found.length === 0) {
            return res.status(404).json({ message: "Blog not found." });
        }

        if (found[0].user_id !== user.id && !user.is_admin) {
            return res.status(403).json({ message: "You can only delete your own blogs." });
        }

        await ensureViewsTable();
        await db.execute("DELETE FROM comments WHERE blog_id = ?", [blogId]);
        await db.execute("DELETE FROM blog_views WHERE blog_id = ?", [blogId]);
        await db.execute("DELETE FROM blogs WHERE id = ?", [blogId]);

        res.json({ message: "Blog deleted successfully." });
    } catch (error) {
        console.error("Delete blog error:", error.message);
        res.status(500).json({ message: "Could not delete blog." });
    }
});


/* Increment the view count for a blog owned by the logged-in user. */
app.post("/api/blogs/:id/view", async (req, res) => {
    try {
        const user = await currentUser(req);

        if (!user) {
            return res.status(401).json({ message: "Please log in to update blog views." });
        }

        const blogId = Number(req.params.id);

        if (!Number.isInteger(blogId) || blogId <= 0) {
            return res.status(400).json({ message: "Invalid blog ID." });
        }

        const [found] = await db.execute("SELECT user_id FROM blogs WHERE id = ?", [blogId]);

        if (found.length === 0) {
            return res.status(404).json({ message: "Blog not found." });
        }

        // The author's own reads and repeat reads do not count.
        if (found[0].user_id !== user.id) {
            await ensureViewsTable();
            const [inserted] = await db.execute(
                "INSERT IGNORE INTO blog_views (blog_id, user_id) VALUES (?, ?)",
                [blogId, user.id]
            );

            if (inserted.affectedRows === 1) {
                await db.execute("UPDATE blogs SET views = views + 1 WHERE id = ?", [blogId]);
            }
        }

        const [rows] = await db.execute("SELECT views FROM blogs WHERE id = ?", [blogId]);

        res.json({ message: "Blog view updated.", views: rows[0].views });
    } catch (error) {
        console.error("Update blog views error:", error.message);
        res.status(500).json({ message: "Could not update blog views." });
    }
});




const ADMIN_EMAIL = (process.env.ADMIN_EMAIL || "").trim().toLowerCase();

function isAdminEmail(email) {
    return Boolean(ADMIN_EMAIL) && String(email).trim().toLowerCase() === ADMIN_EMAIL;
}

async function currentUser(req) {
    if (!req.session.userId) {
        return null;
    }

    const [rows] = await db.execute(
        "SELECT id, username, email FROM users WHERE id = ?",
        [req.session.userId]
    );

    if (rows.length === 0) {
        return null;
    }

    return { ...rows[0], is_admin: isAdminEmail(rows[0].email) };
}

let viewsTableReady = null;

function ensureViewsTable() {
    if (!viewsTableReady) {
        viewsTableReady = db.query(
            `CREATE TABLE IF NOT EXISTS blog_views (
                blog_id INT NOT NULL,
                user_id INT NOT NULL,
                PRIMARY KEY (blog_id, user_id)
            )`
        ).catch((error) => {
            viewsTableReady = null;
            throw error;
        });
    }

    return viewsTableReady;
}

function validPassword(password) {
    return typeof password === "string" && password.length >= 8 && password.length <= 72;
}

async function checkPassword(userId, password) {
    if (typeof password !== "string") {
        return false;
    }

    const [rows] = await db.execute("SELECT password_hash FROM users WHERE id = ?", [userId]);

    return rows.length > 0 && (await bcrypt.compare(password, rows[0].password_hash));
}

async function deleteUserCascade(userId) {
    await ensureViewsTable();
    const connection = await db.getConnection();

    try {
        await connection.beginTransaction();
        await connection.execute(
            "DELETE FROM comments WHERE user_id = ? OR blog_id IN (SELECT id FROM blogs WHERE user_id = ?)",
            [userId, userId]
        );
        await connection.execute(
            "DELETE FROM blog_views WHERE user_id = ? OR blog_id IN (SELECT id FROM blogs WHERE user_id = ?)",
            [userId, userId]
        );
        await connection.execute("DELETE FROM blogs WHERE user_id = ?", [userId]);
        await connection.execute("DELETE FROM users WHERE id = ?", [userId]);
        await connection.commit();
    } catch (error) {
        await connection.rollback();
        throw error;
    } finally {
        connection.release();
    }
}

async function requireAdmin(req, res) {
    const user = await currentUser(req);

    if (!user) {
        res.status(401).json({ message: "Please log in." });
        return null;
    }

    if (!user.is_admin) {
        res.status(403).json({ message: "Admin access required." });
        return null;
    }

    return user;
}

/* Every blog with its author, visible to everyone. */
app.get("/api/blogs/all", async (req, res) => {
    try {
        const [blogs] = await db.execute(
            `SELECT
                b.id,
                b.user_id,
                u.username AS author,
                b.title,
                b.content,
                b.views,
                b.created_at,
                (SELECT COUNT(*) FROM comments c WHERE c.blog_id = b.id) AS comment_count
             FROM blogs b
             JOIN users u ON u.id = b.user_id
             ORDER BY b.created_at DESC`
        );

        res.json({ blogs });
    } catch (error) {
        console.error("Fetch all blogs error:", error.message);
        res.status(500).json({ message: "Could not load blogs." });
    }
});

/* Change the logged-in user's password. */
app.post("/api/account/password", async (req, res) => {
    try {
        const user = await currentUser(req);

        if (!user) {
            return res.status(401).json({ message: "Please log in." });
        }

        const { currentPassword, newPassword } = req.body;

        if (!validPassword(newPassword)) {
            return res.status(400).json({ message: "New password must be 8–72 characters long." });
        }

        if (!(await checkPassword(user.id, currentPassword))) {
            return res.status(403).json({ message: "Current password is incorrect." });
        }

        const hash = await bcrypt.hash(newPassword, 12);
        await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", [hash, user.id]);

        res.json({ message: "Password changed." });
    } catch (error) {
        console.error("Change password error:", error.message);
        res.status(500).json({ message: "Could not change password." });
    }
});

/* Delete the logged-in user's account, blogs and comments. */
app.delete("/api/account", async (req, res) => {
    try {
        const user = await currentUser(req);

        if (!user) {
            return res.status(401).json({ message: "Please log in." });
        }

        if (!(await checkPassword(user.id, req.body.password))) {
            return res.status(403).json({ message: "Password is incorrect." });
        }

        await deleteUserCascade(user.id);

        req.session.destroy(() => {
            res.clearCookie("connect.sid", { path: "/" });
            res.json({ message: "Account deleted." });
        });
    } catch (error) {
        console.error("Delete account error:", error.message);
        res.status(500).json({ message: "Could not delete account." });
    }
});

/* Admin: list users. */
app.get("/api/admin/users", async (req, res) => {
    try {
        const admin = await requireAdmin(req, res);

        if (!admin) {
            return;
        }

        const [users] = await db.execute(
            `SELECT u.id, u.username, u.email,
                    (SELECT COUNT(*) FROM blogs b WHERE b.user_id = u.id) AS blog_count
             FROM users u
             ORDER BY u.id`
        );

        res.json({ users });
    } catch (error) {
        console.error("Admin list error:", error.message);
        res.status(500).json({ message: "Could not load users." });
    }
});

/* Admin: reset any user's password. */
app.post("/api/admin/users/:id/password", async (req, res) => {
    try {
        const admin = await requireAdmin(req, res);

        if (!admin) {
            return;
        }

        const userId = Number(req.params.id);

        if (!Number.isInteger(userId) || userId <= 0) {
            return res.status(400).json({ message: "Invalid user ID." });
        }

        if (!validPassword(req.body.newPassword)) {
            return res.status(400).json({ message: "Password must be 8–72 characters long." });
        }

        const hash = await bcrypt.hash(req.body.newPassword, 12);
        const [result] = await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", [hash, userId]);

        if (result.affectedRows === 0) {
            return res.status(404).json({ message: "User not found." });
        }

        res.json({ message: "Password reset." });
    } catch (error) {
        console.error("Admin reset error:", error.message);
        res.status(500).json({ message: "Could not reset password." });
    }
});

/* Admin: delete any other user and their content. */
app.delete("/api/admin/users/:id", async (req, res) => {
    try {
        const admin = await requireAdmin(req, res);

        if (!admin) {
            return;
        }

        const userId = Number(req.params.id);

        if (!Number.isInteger(userId) || userId <= 0) {
            return res.status(400).json({ message: "Invalid user ID." });
        }

        if (userId === admin.id) {
            return res.status(400).json({ message: "Use Delete account for your own account." });
        }

        await deleteUserCascade(userId);

        res.json({ message: "User deleted." });
    } catch (error) {
        console.error("Admin delete error:", error.message);
        res.status(500).json({ message: "Could not delete user." });
    }
});


/* Availability check (like Instagram's live username check). */
app.get("/api/check", async (req, res) => {
    try {
        const user = await currentUser(req);
        const excludeId = user ? user.id : 0;
        const result = {};
        const fields = {};

        if (typeof req.query.username === "string") fields.username = req.query.username;
        if (typeof req.query.email === "string") fields.email = req.query.email;

        const conflicts = await findConflicts(fields, excludeId);

        if (fields.username !== undefined) {
            const msg = checkUsernameRules(fields.username) || conflicts.username || null;
            result.username = { ok: !msg, message: msg || "Username is available." };
        }

        if (fields.email !== undefined) {
            let msg = checkEmailRules(fields.email) || conflicts.email || null;
            if (!msg && ADMIN_EMAIL && emailKey(fields.email) === emailKey(ADMIN_EMAIL) && !(user && user.is_admin)) {
                msg = "That email is reserved.";
            }
            result.email = { ok: !msg, message: msg || "Email is available." };
        }

        res.json(result);
    } catch (error) {
        console.error("Check error:", error.message);
        res.status(500).json({ message: "Could not check availability." });
    }
});

/* Update username and/or email. Email needs the current password. */
app.post("/api/account/profile", async (req, res) => {
    const release = await acquireLock();

    try {
        const user = await currentUser(req);
        if (!user) return res.status(401).json({ message: "Please log in." });

        const body = req.body || {};
        const newName = typeof body.username === "string" ? body.username.trim() : undefined;
        const newEmail = typeof body.email === "string" ? body.email.trim() : undefined;

        const nameChanged = newName !== undefined && newName !== user.username;
        const emailChanged = newEmail !== undefined && newEmail.toLowerCase() !== user.email.toLowerCase();

        if (!nameChanged && !emailChanged) {
            return res.json({ message: "Nothing to change." });
        }

        if (nameChanged) {
            const nameError = checkUsernameRules(newName);
            if (nameError) return res.status(400).json({ message: nameError });
        }

        if (emailChanged) {
            if (user.is_admin) {
                return res.status(403).json({ message: "The admin email cannot be changed." });
            }

            const emailError = checkEmailRules(newEmail);
            if (emailError) return res.status(400).json({ message: emailError });

            if (ADMIN_EMAIL && emailKey(newEmail) === emailKey(ADMIN_EMAIL)) {
                return res.status(400).json({ message: "That email is reserved." });
            }

            if (!(await checkPassword(user.id, body.password))) {
                return res.status(403).json({ message: "Password is incorrect." });
            }
        }

        const fields = {};
        if (nameChanged) fields.username = newName;
        if (emailChanged) fields.email = newEmail;

        const conflicts = await findConflicts(fields, user.id);
        if (conflicts.username) return res.status(409).json({ message: conflicts.username });
        if (conflicts.email) return res.status(409).json({ message: conflicts.email });

        const connection = await db.getConnection();

        try {
            await connection.beginTransaction();

            if (nameChanged) {
                await connection.execute("UPDATE users SET username = ? WHERE id = ?", [newName, user.id]);
                await connection.execute("UPDATE comments SET name = ? WHERE user_id = ?", [newName, user.id]);
            }

            if (emailChanged) {
                await connection.execute("UPDATE users SET email = ? WHERE id = ?", [newEmail, user.id]);
            }

            await connection.commit();
        } catch (error) {
            await connection.rollback();
            throw error;
        } finally {
            connection.release();
        }

        res.json({ message: "Profile updated." });
    } catch (error) {
        console.error("Update profile error:", error.message);
        res.status(500).json({ message: "Could not update profile." });
    } finally {
        release();
    }
});


/* del-comment */
app.delete("/api/comments/:id", async (req, res) => {
    try {
        const user = await currentUser(req);
        if (!user) return res.status(401).json({ message: "Please log in." });

        const commentId = Number(req.params.id);
        if (!Number.isInteger(commentId) || commentId <= 0) {
            return res.status(400).json({ message: "Invalid comment ID." });
        }

        const [rows] = await db.execute(
            `SELECT c.user_id AS commenter_id, b.user_id AS author_id
             FROM comments c JOIN blogs b ON b.id = c.blog_id
             WHERE c.id = ?`,
            [commentId]
        );

        if (rows.length === 0) return res.status(404).json({ message: "Comment not found." });

        const allowed = user.is_admin
            || rows[0].commenter_id === user.id
            || rows[0].author_id === user.id;

        if (!allowed) return res.status(403).json({ message: "You can't delete this comment." });

        await db.execute("DELETE FROM comments WHERE id = ?", [commentId]);
        res.json({ message: "Comment deleted." });
    } catch (error) {
        console.error("Delete comment error:", error.message);
        res.status(500).json({ message: "Could not delete comment." });
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
        const port = Number(process.env.PORT || 3000);

        app.listen(port, "0.0.0.0", () => {
            console.log(`BlogDrop backend listening on port ${port}`);
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
