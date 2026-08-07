"use client";

import { useEffect } from "react";
import { useUser } from "@clerk/nextjs";

import { posthog, posthogEnabled } from "../lib/posthog";

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export function PostHogIdentify() {
  if (!clerkEnabled || !posthogEnabled) return null;
  return <Identify />;
}

function Identify() {
  const { user, isLoaded, isSignedIn } = useUser();

  useEffect(() => {
    if (!isLoaded) return;
    if (isSignedIn && user) {
      posthog.identify(user.id, {
        email: user.primaryEmailAddress?.emailAddress,
        name: user.fullName,
      });
    } else {
      posthog.reset();
    }
  }, [isLoaded, isSignedIn, user]);

  return null;
}
