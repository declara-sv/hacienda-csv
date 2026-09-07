using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Accounting.Api.Migrations
{
    /// <inheritdoc />
    public partial class GenerationRuns : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // Existing artifacts were produced by the placeholder per-file pipeline and have no value.
            // They must go before ParseJobId is replaced by a non-null GenerationRunId.
            migrationBuilder.Sql("DELETE FROM output_artifacts;");

            migrationBuilder.DropForeignKey(
                name: "FK_output_artifacts_parse_jobs_ParseJobId",
                table: "output_artifacts");

            migrationBuilder.DropTable(
                name: "parse_jobs");

            migrationBuilder.RenameColumn(
                name: "ParseJobId",
                table: "output_artifacts",
                newName: "GenerationRunId");

            migrationBuilder.RenameIndex(
                name: "IX_output_artifacts_ParseJobId",
                table: "output_artifacts",
                newName: "IX_output_artifacts_GenerationRunId");

            migrationBuilder.CreateTable(
                name: "generation_runs",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    ClientId = table.Column<Guid>(type: "uuid", nullable: false),
                    FilingPeriodId = table.Column<Guid>(type: "uuid", nullable: false),
                    RequestedByUserId = table.Column<Guid>(type: "uuid", nullable: false),
                    Version = table.Column<int>(type: "integer", nullable: false),
                    Status = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    ErrorMessage = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true),
                    CreatedAtUtc = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    StartedAtUtc = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CompletedAtUtc = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_generation_runs", x => x.Id);
                    table.ForeignKey(
                        name: "FK_generation_runs_clients_ClientId",
                        column: x => x.ClientId,
                        principalTable: "clients",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_generation_runs_filing_periods_FilingPeriodId",
                        column: x => x.FilingPeriodId,
                        principalTable: "filing_periods",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_generation_runs_users_RequestedByUserId",
                        column: x => x.RequestedByUserId,
                        principalTable: "users",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "generation_run_files",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    GenerationRunId = table.Column<Guid>(type: "uuid", nullable: false),
                    UploadId = table.Column<Guid>(type: "uuid", nullable: true),
                    OriginalFileName = table.Column<string>(type: "character varying(260)", maxLength: 260, nullable: false),
                    SourceFileKind = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    Status = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    ErrorMessage = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_generation_run_files", x => x.Id);
                    table.ForeignKey(
                        name: "FK_generation_run_files_generation_runs_GenerationRunId",
                        column: x => x.GenerationRunId,
                        principalTable: "generation_runs",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_generation_run_files_uploads_UploadId",
                        column: x => x.UploadId,
                        principalTable: "uploads",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                });

            migrationBuilder.CreateIndex(
                name: "IX_generation_run_files_GenerationRunId_UploadId",
                table: "generation_run_files",
                columns: new[] { "GenerationRunId", "UploadId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_generation_run_files_UploadId",
                table: "generation_run_files",
                column: "UploadId");

            migrationBuilder.CreateIndex(
                name: "IX_generation_runs_active_per_period",
                table: "generation_runs",
                column: "FilingPeriodId",
                unique: true,
                filter: "\"Status\" IN ('Pending', 'Running')");

            migrationBuilder.CreateIndex(
                name: "IX_generation_runs_ClientId",
                table: "generation_runs",
                column: "ClientId");

            migrationBuilder.CreateIndex(
                name: "IX_generation_runs_FilingPeriodId_Version",
                table: "generation_runs",
                columns: new[] { "FilingPeriodId", "Version" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_generation_runs_RequestedByUserId",
                table: "generation_runs",
                column: "RequestedByUserId");

            migrationBuilder.CreateIndex(
                name: "IX_generation_runs_Status_CreatedAtUtc",
                table: "generation_runs",
                columns: new[] { "Status", "CreatedAtUtc" });

            migrationBuilder.AddForeignKey(
                name: "FK_output_artifacts_generation_runs_GenerationRunId",
                table: "output_artifacts",
                column: "GenerationRunId",
                principalTable: "generation_runs",
                principalColumn: "Id",
                onDelete: ReferentialAction.Cascade);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_output_artifacts_generation_runs_GenerationRunId",
                table: "output_artifacts");

            migrationBuilder.DropTable(
                name: "generation_run_files");

            migrationBuilder.DropTable(
                name: "generation_runs");

            migrationBuilder.RenameColumn(
                name: "GenerationRunId",
                table: "output_artifacts",
                newName: "ParseJobId");

            migrationBuilder.RenameIndex(
                name: "IX_output_artifacts_GenerationRunId",
                table: "output_artifacts",
                newName: "IX_output_artifacts_ParseJobId");

            migrationBuilder.CreateTable(
                name: "parse_jobs",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    UploadId = table.Column<Guid>(type: "uuid", nullable: false),
                    CompletedAtUtc = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CreatedAtUtc = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    ErrorMessage = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true),
                    StartedAtUtc = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    Status = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_parse_jobs", x => x.Id);
                    table.ForeignKey(
                        name: "FK_parse_jobs_uploads_UploadId",
                        column: x => x.UploadId,
                        principalTable: "uploads",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_parse_jobs_Status_CreatedAtUtc",
                table: "parse_jobs",
                columns: new[] { "Status", "CreatedAtUtc" });

            migrationBuilder.CreateIndex(
                name: "IX_parse_jobs_UploadId",
                table: "parse_jobs",
                column: "UploadId");

            migrationBuilder.AddForeignKey(
                name: "FK_output_artifacts_parse_jobs_ParseJobId",
                table: "output_artifacts",
                column: "ParseJobId",
                principalTable: "parse_jobs",
                principalColumn: "Id",
                onDelete: ReferentialAction.Cascade);
        }
    }
}
