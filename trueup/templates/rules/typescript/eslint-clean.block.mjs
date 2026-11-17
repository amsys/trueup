// Managed by trueup. Edit trueup.toml, then run the trueup skill.
// The TypeScript block of lint/typescript/eslint.config.mjs, clean mode:
// the comment standard (jsdoc, ts-comment and disable-comment reasons),
// typescript-eslint's recommended rules, and eslint-plugin-security's
// recommended rules (SAST, D7.5), over every JS and TS file.
import tseslint from "typescript-eslint";
import jsdoc from "eslint-plugin-jsdoc";
import eslintComments from "@eslint-community/eslint-plugin-eslint-comments";
import pluginSecurity from "eslint-plugin-security";

/** The TypeScript and JavaScript block, clean mode. */
const tsBlock = {
  files: ["**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs}"],
  extends: [
    tseslint.configs.base,
    tseslint.configs.recommended,
    jsdoc.configs["flat/recommended-typescript-error"],
    pluginSecurity.configs.recommended,
  ],
  plugins: {
    "eslint-comments": eslintComments,
  },
  rules: {
    "@typescript-eslint/ban-ts-comment": [
      "error",
      { "ts-expect-error": "allow-with-description" },
    ],
    "eslint-comments/require-description": "error",
  },
};
