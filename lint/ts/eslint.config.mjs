// arch: D1.5
// eslint flat configuration for the TypeScript comment standard.
import tseslint from "typescript-eslint";
import jsdoc from "eslint-plugin-jsdoc";
import eslintComments from "@eslint-community/eslint-plugin-eslint-comments";

export default tseslint.config(
  {
    files: ["**/*.ts"],
    extends: [
      tseslint.configs.base,
      jsdoc.configs["flat/recommended-typescript-error"],
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
  },
);
