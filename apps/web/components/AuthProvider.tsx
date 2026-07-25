import { ClerkProvider } from "@clerk/nextjs";

import { AuthTokenBridge } from "./AuthTokenBridge";

const clerkPublishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

export function AuthProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  if (!clerkPublishableKey) {
    return <>{children}</>;
  }

  return (
    <ClerkProvider>
      <AuthTokenBridge />
      {children}
    </ClerkProvider>
  );
}
