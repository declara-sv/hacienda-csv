import { vi } from 'vitest'
import type { ReactNode } from 'react'

/**
 * Clerk needs a browser session and a publishable key; tests get a signed-in
 * stand-in instead. Override per test with vi.mocked(...) when needed.
 */
vi.mock('@clerk/tanstack-react-start', () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
  Show: ({ when, children }: { when: string; children: ReactNode }) =>
    when === 'signed-in' ? children : null,
  SignIn: () => null,
  SignUp: () => null,
  UserButton: () => null,
  getToken: vi.fn(async () => 'test-token'),
  useAuth: vi.fn(() => ({
    isLoaded: true,
    isSignedIn: true,
    userId: 'user_test',
    getToken: async () => 'test-token',
  })),
  useClerk: vi.fn(() => ({ isSignedIn: true, signOut: vi.fn() })),
}))
