/**
 * Next.js API health proxy to FastAPI backend.
 */

import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8002";

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/health`);
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        status: "error",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 503 },
    );
  }
}
