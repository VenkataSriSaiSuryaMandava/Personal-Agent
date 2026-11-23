/**
 * Server-only backend destination.
 *
 * The address is fixed at deployment time, never supplied by
 * a browser request. No arbitrary remote destinations are allowed.
 */
export function backendOrigin(): string {
  const configured =
    process.env.AEGIS_INTERNAL_BACKEND_URL ??
    "http://127.0.0.1:8000";

  if (
    configured !== "http://127.0.0.1:8000" &&
    configured !== "http://backend:8000"
  ) {
    throw new Error(
      "Unsupported internal backend configuration"
    );
  }

  return configured;
}
