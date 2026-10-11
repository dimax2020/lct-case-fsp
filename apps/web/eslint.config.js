import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    ignores: [".nuxt/**", ".output/**", "node_modules/**", "app/**", "public/**"],
  },
];
