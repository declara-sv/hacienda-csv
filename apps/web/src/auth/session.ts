import { auth } from '@clerk/tanstack-react-start/server'
import { createServerFn } from '@tanstack/react-start'

/** Reads the Clerk session from the request cookies on the server. */
export const fetchAuthState = createServerFn({ method: 'GET' }).handler(
  async () => {
    const { isAuthenticated, userId } = await auth()
    return { isAuthenticated, userId }
  },
)

type BrowserClerk = { loaded: boolean; isSignedIn: boolean }

function loadedBrowserClerk(): BrowserClerk | undefined {
  if (typeof window === 'undefined') return undefined
  const clerk = (window as { Clerk?: BrowserClerk }).Clerk
  return clerk?.loaded ? clerk : undefined
}

/**
 * Whether the visitor has a Clerk session. Once Clerk has loaded in the
 * browser its state is used directly; otherwise (SSR, first navigation) the
 * server function asks Clerk on the server.
 */
export async function isSignedIn(): Promise<boolean> {
  const clerk = loadedBrowserClerk()
  if (clerk) return clerk.isSignedIn

  const { isAuthenticated } = await fetchAuthState()
  return isAuthenticated
}
