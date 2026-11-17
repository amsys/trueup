// Managed by trueup. Edit trueup.toml, then run the trueup skill.
// The Vue block of lint/typescript/eslint.config.mjs, strict mode:
// eslint-plugin-vue's recommended rules, the TypeScript parser for the
// script part, a TypeScript script in each `.vue` file, and limits on
// template depth, props and block length, and the shared script thresholds
// (cyclomatic 10, nesting 4, 5 parameters, function 60 lines, cognitive
// 15). It follows the TypeScript
// block, which imports `tseslint` and already applies
// eslint-plugin-security's recommended rules (SAST, D7.5) to the
// project's JS and TS files.
import pluginVue from "eslint-plugin-vue";
import vueSonar from "eslint-plugin-sonarjs";

/** The Vue blocks, strict mode. */
const vueBlocks = [
  ...pluginVue.configs["flat/recommended"],
  {
    files: ["**/*.vue"],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
    plugins: { sonarjs: vueSonar },
    rules: {
      "complexity": ["error", 10],
      "max-depth": ["error", 4],
      "max-params": ["error", 5],
      "max-lines-per-function": ["error", { max: 60, skipBlankLines: true, skipComments: true }],
      "sonarjs/cognitive-complexity": ["error", 15],
      "vue/block-lang": ["error", { script: { lang: "ts" } }],
      "vue/max-template-depth": ["error", { maxDepth: 8 }],
      "vue/max-props": ["error", { maxProps: 10 }],
      "vue/max-lines-per-block": ["error", { template: 200, script: 300, style: 200, skipBlankLines: true }],
    },
  },
];
