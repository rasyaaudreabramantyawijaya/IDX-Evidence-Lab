import { render, screen } from "@testing-library/react";
import { App } from "./App";

afterEach(() => vi.restoreAllMocks());

test("shows the document count when the backend answers", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(
            JSON.stringify({ ok: true, openrouter_configured: false, local_documents: 12 }),
        ),
    );
    render(<App />);
    expect(await screen.findByText(/12 dokumen lokal/)).toBeInTheDocument();
});

test("shows an alert when the backend is unreachable", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network"));
    render(<App />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
});
