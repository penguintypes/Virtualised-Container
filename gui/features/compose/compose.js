(() => {
  const find = (selector) => document.querySelector(selector);
  const template = `name: example

services:
  web:
    image: nginx
    ports:
      - "8080:80"
`;
  let editingName = null;

  function showResult(message, type = "") {
    const result = find("#compose-result");
    result.textContent = message;
    result.className = type;
  }

  function open() {
    const dialog = find("#compose-dialog");
    const editorElement = find("#compose-editor");

    window.vcontainerComposeEditor.start(editorElement);
    window.vcontainerComposeEditor.setText(template);
    editingName = null;
    find("#compose-dialog-title").textContent = "New Compose project";
    find("#compose-start").hidden = false;
    find("#compose-save").hidden = true;
    showResult("");
    if (!dialog.open) dialog.showModal();
  }

  function edit(name, source) {
    const dialog = find("#compose-dialog");
    window.vcontainerComposeEditor.start(find("#compose-editor"));
    window.vcontainerComposeEditor.setText(source);
    editingName = name;
    find("#compose-dialog-title").textContent = `Edit ${name}`;
    find("#compose-start").hidden = true;
    find("#compose-save").hidden = false;
    showResult("Changes are saved without restarting running containers.");
    if (!dialog.open) dialog.showModal();
  }

  async function request(path, method = "POST") {
    const response = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        yaml: window.vcontainerComposeEditor.getText(),
      }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "Compose request failed");
    }
    return result;
  }

  async function validate() {
    try {
      window.vcontainerComposeEditor.parse();
      const result = await request("/compose/validate");
      showResult(
        `Valid Compose YAML: ${result.services.length} service(s) found`,
        "success",
      );
      return result;
    } catch (error) {
      showResult(error.message, "error");
      return null;
    }
  }

  async function start() {
    const button = find("#compose-start");
    button.disabled = true;
    showResult("Validating Compose project…");

    try {
      if (!(await validate())) return;
      showResult("Starting Compose services…");
      const result = await request("/compose/up");
      showResult(
        `Started ${result.containers.length} service(s)`,
        "success",
      );
      window.dispatchEvent(new CustomEvent("compose-changed"));
    } catch (error) {
      showResult(error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function save() {
    if (!editingName || !(await validate())) return;
    const button = find("#compose-save");
    button.disabled = true;
    showResult("Saving Compose YAML…");
    try {
      await request(`/compose/${encodeURIComponent(editingName)}`, "PUT");
      showResult(
        "YAML saved. Running containers keep their current configuration.",
        "success",
      );
      window.dispatchEvent(new CustomEvent("compose-changed"));
    } catch (error) {
      showResult(error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function upload(event) {
    const [file] = event.target.files;
    if (!file) return;

    try {
      window.vcontainerComposeEditor.setText(await file.text());
      showResult(`Loaded ${file.name}`, "success");
    } catch (error) {
      showResult(`Could not read file: ${error.message}`, "error");
    } finally {
      event.target.value = "";
    }
  }

  find("#compose-upload")?.addEventListener("click", () => {
    find("#compose-file").click();
  });
  find("#compose-file")?.addEventListener("change", upload);
  find("#compose-validate")?.addEventListener("click", validate);
  find("#compose-start")?.addEventListener("click", start);
  find("#compose-save")?.addEventListener("click", save);

  window.vcontainerCompose = { edit, open, save, start, validate };
})();
