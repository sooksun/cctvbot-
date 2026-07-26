import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppHeader from "@/components/AppHeader";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

describe("AppHeader", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows the admin camera link + logout for an admin", () => {
    localStorage.setItem("cctvbot_role", "admin");
    localStorage.setItem("cctvbot_username", "admin1");
    render(<AppHeader />);
    expect(screen.getByText("จัดการกล้อง")).toBeInTheDocument();
    expect(screen.getByText("เปลี่ยนรหัสผ่าน")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "ออกจากระบบ" }),
    ).toBeInTheDocument();
  });

  it("hides the camera link for a viewer", () => {
    localStorage.setItem("cctvbot_role", "viewer");
    render(<AppHeader />);
    expect(screen.queryByText("จัดการกล้อง")).toBeNull();
  });
});
