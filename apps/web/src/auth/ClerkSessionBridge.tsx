import { useAuth, useClerk } from '@clerk/tanstack-react-start'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'
import { setUnauthorizedHandler } from '#/lib/api-client'
import { SIGN_IN_PATH } from './paths'

/**
 * Connects Clerk to the non-React parts of the app: sends the user to sign-in
 * when the API rejects the token, and drops cached data when the user changes.
 */
export function ClerkSessionBridge() {
  const clerk = useClerk()
  const { isLoaded, userId } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()

  useEffect(
    () =>
      setUnauthorizedHandler(async () => {
        // The API rejected a token Clerk still considers valid: end the Clerk
        // session too, otherwise sign-in would bounce straight back here.
        if (clerk.isSignedIn) {
          await clerk.signOut({ redirectUrl: SIGN_IN_PATH })
          return
        }
        await router.navigate({ to: SIGN_IN_PATH })
      }),
    [clerk, router],
  )

  const previousUserId = useRef<string | null | undefined>(undefined)
  useEffect(() => {
    if (!isLoaded) return
    const current = userId ?? null
    if (
      previousUserId.current !== undefined &&
      previousUserId.current !== current
    ) {
      queryClient.clear()
    }
    previousUserId.current = current
  }, [isLoaded, userId, queryClient])

  return null
}
