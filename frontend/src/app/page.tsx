import { Suspense } from "react";
import { connection } from "next/server";

import WorkspaceApp from "./WorkspaceApp";

async function RuntimeWorkspace() {
  await connection();

  const publicMode =
    process.env.AEGIS_RUNTIME_MODE === "public";

  return <WorkspaceApp publicMode={publicMode} />;


}

export default function Home() {
  return (
    <Suspense fallback={
      <main className="aegis-auth-screen">
        <p role="status">Loading Aegis workspace…</p>
      </main>
    }>
      <RuntimeWorkspace />
    </Suspense>
  );
}
