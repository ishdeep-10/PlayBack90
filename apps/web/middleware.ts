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

// Behind a reverse proxy, `request.url` reflects the container's own bind
// address (e.g. 0.0.0.0:3000) rather than the public host, even though the
// forwarded headers are correct. Build the public-facing URL from those
// headers instead of trusting `request.url`.
function publicUrl(request: NextRequest) {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? request.nextUrl.host;
  const protocol = request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol.replace(":", "");
  return `${protocol}://${host}${request.nextUrl.pathname}${request.nextUrl.search}`;
}

const protectedMiddleware = clerkEnabled
  ? clerkMiddleware(async (auth, request) => {
      if (isPublicAuthRoute(request.nextUrl.pathname)) return;

      const session = await auth();
      if (!session.userId) return session.redirectToSignIn({ returnBackUrl: publicUrl(request) });
    })
  : publicMiddleware;

export default protectedMiddleware;

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ico|ttf|woff2?|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
