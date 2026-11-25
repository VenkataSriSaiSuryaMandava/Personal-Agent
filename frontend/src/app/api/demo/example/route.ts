import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json(
    { detail: "Recorded demo responses are no longer available" },
    {
      status: 410,
      headers: { "Cache-Control": "no-store" },
    }
  );
}
