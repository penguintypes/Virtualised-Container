with open("gui/app.js", "r") as f: js = f.read()
js = js.replace(
    ').join(" ")}</div>`;',
    ').join(" ")} <button id="launch-blogdrop" onclick="launchBlogDrop()">Launch BlogDrop</button></div>`;'
)
js = js.replace("async function launchBlogDrop() {", "window.launchBlogDrop = async function() {")
with open("gui/app.js", "w") as f: f.write(js)
