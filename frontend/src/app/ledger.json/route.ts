import { NextRequest, NextResponse } from "next/server";
import { getLedger } from "@/lib/api";

// Raw chain rows for anyone verifying the record. Pages through the API 5,000 rows at a time.
export async function GET(request: NextRequest) {
  const after = Number(request.nextUrl.searchParams.get("after") ?? 0);
  const rows = await getLedger(Number.isFinite(after) && after > 0 ? Math.floor(after) : 0);
  return NextResponse.json(rows, { headers: { "Cache-Control": "public, max-age=60" } });
}
