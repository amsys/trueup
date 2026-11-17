// Managed by trueup. Edit trueup.toml, then run the trueup skill.
// The Vue block of lint/typescript/eslint.config.mjs, clean mode:
// eslint-plugin-vue's essential rules, with the TypeScript parser for the
// script part of each `.vue` file. It follows the TypeScript block, which
// imports `tseslint` and already applies eslint-plugin-security's
// recommended rules (SAST, D7.5) to the project's JS and TS files.
import pluginVue from "eslint-plugin-vue";

/** The Vue blocks, clean mode. */
const vueBlocks = [
  ...pluginVue.configs["flat/essential"],
  {
    files: ["**/*.vue"],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
];
