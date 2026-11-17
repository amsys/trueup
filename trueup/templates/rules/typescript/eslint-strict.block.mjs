// Managed by trueup. Edit trueup.toml, then run the trueup skill.
// The TypeScript block of lint/typescript/eslint.config.mjs, strict mode:
// typescript-eslint's type-checked strict and stylistic rules, sonarjs,
// eslint-plugin-security's recommended rules (SAST, D7.5), and the
// shared thresholds (cognitive 15, cyclomatic 10, function 60 lines, 5
// parameters, nesting 4, file 1000 lines). There is no max-statements
// rule: the function-length rule covers it. The typed rules need a
// tsconfig, so the typed object reads TypeScript files only; a second
// object applies the untyped strict rules to JavaScript files.
import tseslint from "typescript-eslint";
import jsdoc from "eslint-plugin-jsdoc";
import sonarjs from "eslint-plugin-sonarjs";
import eslintComments from "@eslint-community/eslint-plugin-eslint-comments";
import pluginSecurity from "eslint-plugin-security";

/** The rules both objects of the TypeScript block share. */
const sharedRules = {
  "complexity": ["error", 10],
  "max-depth": ["error", 4],
  "max-lines-per-function": ["error", { max: 60, skipBlankLines: true, skipComments: true }],
  "max-params": ["error", 5],
  "max-lines": ["error", 1000],
  "sonarjs/cognitive-complexity": ["error", 15],
  "jsdoc/require-jsdoc": ["error", {
    publicOnly: true,
    require: {
      FunctionDeclaration: true,
      ClassDeclaration: true,
      MethodDefinition: true,
      ArrowFunctionExpression: true,
    },
  }],
  "jsdoc/require-file-overview": "error",
  "eslint-comments/require-description": "error",
};

/** The TypeScript block, strict mode: a typed and an untyped object. */
const tsBlock = [
  {
    files: ["**/*.{ts,tsx,mts,cts}"],
    extends: [
      tseslint.configs.strictTypeChecked,
      tseslint.configs.stylisticTypeChecked,
      jsdoc.configs["flat/recommended-typescript-error"],
      sonarjs.configs.recommended,
      pluginSecurity.configs.recommended,
    ],
    languageOptions: { parserOptions: { projectService: true } },
    plugins: {
      "eslint-comments": eslintComments,
    },
    rules: {
      ...sharedRules,
      "@typescript-eslint/ban-ts-comment": [
        "error",
        { "ts-expect-error": "allow-with-description" },
      ],
    },
  },
  {
    files: ["**/*.{js,jsx,mjs,cjs}"],
    extends: [
      tseslint.configs.strict,
      tseslint.configs.stylistic,
      jsdoc.configs["flat/recommended-error"],
      sonarjs.configs.recommended,
      pluginSecurity.configs.recommended,
    ],
    plugins: {
      "eslint-comments": eslintComments,
    },
    rules: sharedRules,
  },
];
