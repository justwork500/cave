import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./Markdown";

describe("markdown card", () => {
  it("shows raw HTML as plain text", () => {  // Review Focus 4
    const { container } = render(
      <Markdown text={'<script>alert(1)</script>\n<img src=x onerror="alert(2)">'} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(screen.getByText('<img src=x onerror="alert(2)">')).toBeInTheDocument();
  });

  it("supports headings, emphasis, lists and links", () => {
    render(<Markdown text={"# Title\n*soft* and **loud**\n- one\n- two\n1. first\n[docs](https://example.org/x)"} />);
    expect(screen.getByRole("heading", { level: 3, name: "Title" })).toBeInTheDocument();
    expect(screen.getByText("soft").tagName).toBe("EM");
    expect(screen.getByText("loud").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByRole("link", { name: "docs" })).toHaveAttribute("href", "https://example.org/x");
  });

  it("refuses script links", () => {
    render(<Markdown text="[click](javascript:alert(1))" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("click")).toBeInTheDocument();
  });
});
