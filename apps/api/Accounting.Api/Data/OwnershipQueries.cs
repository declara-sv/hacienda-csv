using Accounting.Api.Domain.Entities;
using Microsoft.EntityFrameworkCore;

namespace Accounting.Api.Data;

public static class OwnershipQueries
{
    public static Task<Client?> FindOwnedClientAsync(this AppDbContext dbContext, Guid clientId, Guid userId, CancellationToken cancellationToken)
    {
        return dbContext.Clients.FirstOrDefaultAsync(x => x.Id == clientId && x.OwnerUserId == userId, cancellationToken);
    }

    public static Task<FilingPeriod?> FindOwnedFilingPeriodAsync(this AppDbContext dbContext, Guid clientId, Guid filingPeriodId, Guid userId, CancellationToken cancellationToken)
    {
        return dbContext.FilingPeriods
            .Include(x => x.Client)
            .FirstOrDefaultAsync(
                x => x.Id == filingPeriodId && x.ClientId == clientId && x.Client.OwnerUserId == userId,
                cancellationToken);
    }
}
