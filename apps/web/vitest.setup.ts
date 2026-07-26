import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// globals:false → RTL's auto-cleanup isn't registered; unmount after each test
// so renders don't leak into the next one.
afterEach(() => {
  cleanup();
});
