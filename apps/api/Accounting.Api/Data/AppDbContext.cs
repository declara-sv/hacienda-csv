using Accounting.Api.Domain.Entities;
using Accounting.Api.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace Accounting.Api.Data;

public sealed class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<AppUser> Users => Set<AppUser>();
    public DbSet<RefreshToken> RefreshTokens => Set<RefreshToken>();
    public DbSet<Client> Clients => Set<Client>();
    public DbSet<ClientConfig> ClientConfigs => Set<ClientConfig>();
    public DbSet<FilingPeriod> FilingPeriods => Set<FilingPeriod>();
    public DbSet<Upload> Uploads => Set<Upload>();
    public DbSet<ParseJob> ParseJobs => Set<ParseJob>();
    public DbSet<OutputArtifact> OutputArtifacts => Set<OutputArtifact>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<AppUser>(entity =>
        {
            entity.ToTable("users");
            entity.HasKey(x => x.Id);
            entity.Property(x => x.Email).HasMaxLength(320).IsRequired();
            entity.Property(x => x.NormalizedEmail).HasMaxLength(320).IsRequired();
            entity.Property(x => x.FullName).HasMaxLength(200).IsRequired();
            entity.Property(x => x.PasswordHash).HasMaxLength(2048).IsRequired();
            entity.HasIndex(x => x.NormalizedEmail).IsUnique();
        });

        modelBuilder.Entity<RefreshToken>(entity =>
        {
            entity.ToTable("refresh_tokens");
            entity.HasKey(x => x.Id);
            entity.Property(x => x.TokenHash).HasMaxLength(200).IsRequired();
            entity.HasIndex(x => x.TokenHash).IsUnique();
            entity.HasOne(x => x.User)
                .WithMany(x => x.RefreshTokens)
                .HasForeignKey(x => x.UserId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Client>(entity =>
        {
            entity.ToTable("clients");
            entity.HasKey(x => x.Id);
            entity.Property(x => x.Name).HasMaxLength(160).IsRequired();
            entity.Property(x => x.TaxId).HasMaxLength(32).IsRequired();
            entity.Property(x => x.Notes).HasMaxLength(2000);
            entity.HasIndex(x => new { x.OwnerUserId, x.Name });
            entity.HasOne(x => x.OwnerUser)
                .WithMany(x => x.Clients)
                .HasForeignKey(x => x.OwnerUserId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<ClientConfig>(entity =>
        {
            entity.ToTable("client_configs");
            entity.HasKey(x => x.Id);
            entity.Property(x => x.Name).HasMaxLength(80).IsRequired();
            entity.Property(x => x.PrefillValuesJson).HasColumnType("jsonb").IsRequired();
            entity.Property(x => x.TransformationRulesJson).HasColumnType("jsonb");
            entity.HasOne(x => x.Client)
                .WithMany(x => x.Configurations)
                .HasForeignKey(x => x.ClientId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<FilingPeriod>(entity =>
        {
            entity.ToTable("filing_periods");
            entity.HasKey(x => x.Id);
            entity.Property(x => x.Year).IsRequired();
            entity.Property(x => x.Month).IsRequired();
            entity.HasIndex(x => new { x.ClientId, x.Year, x.Month }).IsUnique();
            entity.HasOne(x => x.Client)
                .WithMany(x => x.FilingPeriods)
                .HasForeignKey(x => x.ClientId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Upload>(entity =>
        {
            entity.ToTable("uploads");
            entity.HasKey(x => x.Id);
            entity.Property(x => x.OriginalFileName).HasMaxLength(260).IsRequired();
            entity.Property(x => x.ContentType).HasMaxLength(120).IsRequired();
            entity.Property(x => x.SourceFileKind).HasMaxLength(20).IsRequired();
            entity.Property(x => x.StorageProvider).HasMaxLength(40).IsRequired();
            entity.Property(x => x.StorageContainer).HasMaxLength(80).IsRequired();
            entity.Property(x => x.StoragePath).HasMaxLength(500).IsRequired();
            entity.HasIndex(x => new { x.ClientId, x.FilingPeriodId, x.CreatedAtUtc });

            entity.HasOne(x => x.Client)
                .WithMany(x => x.Uploads)
                .HasForeignKey(x => x.ClientId)
                .OnDelete(DeleteBehavior.Cascade);
            entity.HasOne(x => x.FilingPeriod)
                .WithMany(x => x.Uploads)
                .HasForeignKey(x => x.FilingPeriodId)
                .OnDelete(DeleteBehavior.Cascade);
            entity.HasOne(x => x.UploadedByUser)
                .WithMany(x => x.Uploads)
                .HasForeignKey(x => x.UploadedByUserId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        modelBuilder.Entity<ParseJob>(entity =>
        {
            entity.ToTable("parse_jobs");
            entity.HasKey(x => x.Id);
            entity.Property(x => x.Status)
                .HasConversion(
                    value => value.ToString(),
                    value => Enum.Parse<ParseJobStatus>(value))
                .HasMaxLength(20)
                .IsRequired();
            entity.Property(x => x.ErrorMessage).HasMaxLength(2000);
            entity.HasIndex(x => new { x.Status, x.CreatedAtUtc });

            entity.HasOne(x => x.Upload)
                .WithMany(x => x.ParseJobs)
                .HasForeignKey(x => x.UploadId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<OutputArtifact>(entity =>
        {
            entity.ToTable("output_artifacts");
            entity.HasKey(x => x.Id);
            entity.Property(x => x.ArtifactKind).HasMaxLength(20).IsRequired();
            entity.Property(x => x.FileName).HasMaxLength(260).IsRequired();
            entity.Property(x => x.ContentType).HasMaxLength(120).IsRequired();
            entity.Property(x => x.StorageProvider).HasMaxLength(40).IsRequired();
            entity.Property(x => x.StorageContainer).HasMaxLength(80).IsRequired();
            entity.Property(x => x.StoragePath).HasMaxLength(500).IsRequired();

            entity.HasOne(x => x.ParseJob)
                .WithMany(x => x.OutputArtifacts)
                .HasForeignKey(x => x.ParseJobId)
                .OnDelete(DeleteBehavior.Cascade);
            entity.HasOne(x => x.Client)
                .WithMany()
                .HasForeignKey(x => x.ClientId)
                .OnDelete(DeleteBehavior.Cascade);
            entity.HasOne(x => x.FilingPeriod)
                .WithMany(x => x.OutputArtifacts)
                .HasForeignKey(x => x.FilingPeriodId)
                .OnDelete(DeleteBehavior.Cascade);
        });
    }
}
