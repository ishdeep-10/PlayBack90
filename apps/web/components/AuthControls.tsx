"use client";

import { SignInButton, UserButton, useUser } from "@clerk/nextjs";

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

function AuthControlsInner() {
  const { isLoaded, isSignedIn } = useUser();

  if (!isLoaded) return null;

  if (isSignedIn) {
    return (
      <div className="nav-auth-controls">
        <UserButton />
      </div>
    );
  }

  return (
    <div className="nav-auth-controls">
      <SignInButton mode="modal">
        <button type="button" className="ghost-button nav-link">Sign in</button>
      </SignInButton>
    </div>
  );
}

export function AuthControls() {
  if (!clerkEnabled) return null;
  return <AuthControlsInner />;
}
