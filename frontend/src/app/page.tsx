import { Suspense } from "react";
import { connection } from "next/server";

import WorkspaceApp from "./WorkspaceApp";

async function RuntimeWorkspace() {
  await connection();

  const ownerAvailable =
    process.env.AEGIS_PUBLIC_DEMO !== "1" &&
    process.env.AEGIS_LOCAL_BACKEND === "1";

  return (
    <WorkspaceApp ownerAvailable={ownerAvailable} />
  );
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
