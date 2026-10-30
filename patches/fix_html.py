with open("gui/index.html", "r") as f: html = f.read()
if 'id="launch-blogdrop"' not in html:
    html = html.replace('>Run runner</button>', '>Run runner</button> <button id="launch-blogdrop">Launch BlogDrop</button>')
    with open("gui/index.html", "w") as f: f.write(html)
