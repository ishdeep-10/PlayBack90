import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
const publicAuthPrefixes = ["/sign-in", "/sign-up"];

function isPublicAuthRoute(pathname: string) {
  return publicAuthPrefixes.some((prefix) => pathname === prefix || pathname.startsWith(prefix + "/" ));
}

function publicMiddleware(_request: NextRequest) {
  return NextResponse.next();
}

const protectedMiddleware = clerkEnabled
  ? clerkMiddleware(async (auth, request) => {
      if (isPublicAuthRoute(request.nextUrl.pathname)) return;

      const session = await auth();
      if (!session.userId) return session.redirectToSignIn({ returnBackUrl: request.url });
    })
  : publicMiddleware;

export default protectedMiddleware;

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ico|ttf|woff2?|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
