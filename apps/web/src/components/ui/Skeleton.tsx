import { cn } from '#/lib/cn'

export function Skeleton({ className }: { className?: string }) {
  return (
    <div aria-hidden className={cn('skeleton rounded-control', className)} />
  )
}

/** Skeleton for a grid of tiles matching the client and period lists. */
export function TileGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          className="rounded-container border border-line bg-surface-raised p-4"
        >
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="mt-2 h-4 w-1/3" />
          <Skeleton className="mt-5 h-4 w-1/4" />
        </div>
      ))}
    </div>
  )
}

/** Skeleton for stacked rows matching the uploads history. */
export function RowListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="divide-y divide-line" aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex items-start gap-4 py-4">
          <Skeleton className="size-10 shrink-0" />
          <div className="flex-1">
            <Skeleton className="h-5 w-1/2" />
            <Skeleton className="mt-2 h-4 w-1/3" />
            <Skeleton className="mt-4 h-8 w-40 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  )
}

/** Full-page placeholder used while the session is being read or redirected. */
export function PageSkeleton() {
  return (
    <div aria-hidden className="space-y-8">
      <div>
        <Skeleton className="h-9 w-56" />
        <Skeleton className="mt-3 h-5 w-96 max-w-full" />
      </div>
      <TileGridSkeleton count={3} />
    </div>
  )
}
