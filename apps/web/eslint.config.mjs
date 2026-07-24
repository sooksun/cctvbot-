import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

// Next 16's eslint-config-next ships native flat configs (spreadable arrays),
// so we import them directly instead of the legacy FlatCompat.extends() shim.
const eslintConfig = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    // Surfaced by the Next 16 react-hooks plugin. Our three hits are
    // intentional client-only patterns (AuthGate gate + on-mount data loads)
    // that setState in an effect specifically to stay SSR/hydration-safe.
    // Keep as a warning for visibility instead of failing lint.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
    ],
  },
];

export default eslintConfig;
