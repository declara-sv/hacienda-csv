namespace Accounting.Api.Storage;

public sealed class StorageOptions
{
    public const string SectionName = "Storage";

    public string Provider { get; set; } = "Local";

    public string UploadContainer { get; set; } = "uploads";
    public string OutputContainer { get; set; } = "outputs";

    public string LocalRootPath { get; set; } = "App_Data/files";
    public string? AzureBlobConnectionString { get; set; }
}
