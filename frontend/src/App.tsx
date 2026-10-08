import { useEffect, useState } from "react";
import { getHealth, type Health } from "./api/client";

type State = { status: "loading" } | { status: "error" } | { status: "ready"; health: Health };

// Placeholder shell: proves the toolchain and the proxy to the Python backend work.
export function App() {
    const [state, setState] = useState<State>({ status: "loading" });

    useEffect(() => {
        const controller = new AbortController();
        getHealth(controller.signal)
            .then((health) => setState({ status: "ready", health }))
            .catch((error: unknown) => {
                if (!(error instanceof DOMException && error.name === "AbortError")) {
                    setState({ status: "error" });
                }
            });
        return () => controller.abort();
    }, []);

    return (
        <main className="shell">
            <h1>IDX Evidence Lab</h1>
            {state.status === "loading" && <p>Memuat…</p>}
            {state.status === "error" && <p role="alert">Server lokal tidak terhubung.</p>}
            {state.status === "ready" && (
                <p>Server terhubung. {state.health.local_documents} dokumen lokal.</p>
            )}
        </main>
    );
}
