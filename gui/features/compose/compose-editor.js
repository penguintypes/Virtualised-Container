import { basicSetup } from "codemirror";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { yaml as yamlLanguage } from "@codemirror/lang-yaml";
import { oneDark } from "@codemirror/theme-one-dark";
import YAML from "yaml";

let editor = null;

const template = `name: example

services:
  web:
    image: nginx
    ports:
      - "8080:80"
`;

function start(parent) {
  if (editor) {
    return editor;
  }

  editor = new EditorView({
    parent,
    state: EditorState.create({
      doc: template,
      extensions: [
        basicSetup,
        yamlLanguage(),
        oneDark,
        EditorView.lineWrapping,
      ],
    }),
  });

  return editor;
}

function getText() {
  return editor?.state.doc.toString() ?? "";
}

function setText(text) {
  if (!editor) {
    throw new Error("Compose editor has not started");
  }

  editor.dispatch({
    changes: {
      from: 0,
      to: editor.state.doc.length,
      insert: text,
    },
  });
}

function parse() {
  const project = YAML.parse(getText());

  if (!project || typeof project !== "object") {
    throw new Error("Compose YAML must contain an object");
  }

  if (!project.services || typeof project.services !== "object") {
    throw new Error("Compose YAML requires a services section");
  }

  if (Object.keys(project.services).length === 0) {
    throw new Error("At least one service is required");
  }

  return project;
}

window.vcontainerComposeEditor = {
  start,
  getText,
  setText,
  parse,
};