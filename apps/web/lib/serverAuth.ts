import "server-only";

import { auth } from "@clerk/nextjs/server";

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export async function getServerAuthToken(): Promise<string | null> {
  if (!clerkEnabled) return null;

  try {
    const session = await auth();
    return session.getToken();
  } catch {
    return null;
  }
}
