using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;
using Microsoft.Extensions.Options;

namespace Accounting.Api.Storage;

public sealed class AzureBlobFileStorage(IOptions<StorageOptions> options) : IFileStorage
{
    private readonly StorageOptions _options = options.Value;
    public string ProviderName => "AzureBlob";

    public async Task<StoredFileReference> SaveAsync(
        string container,
        string path,
        Stream content,
        string contentType,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(_options.AzureBlobConnectionString))
        {
            throw new InvalidOperationException("Storage:AzureBlobConnectionString no está configurado.");
        }

        var client = new BlobContainerClient(_options.AzureBlobConnectionString, container);
        await client.CreateIfNotExistsAsync(cancellationToken: cancellationToken);

        var blobClient = client.GetBlobClient(path);
        await blobClient.UploadAsync(content, new BlobUploadOptions
        {
            HttpHeaders = new BlobHttpHeaders
            {
                ContentType = contentType,
            },
        }, cancellationToken);

        return new StoredFileReference(ProviderName, container, path);
    }

    public async Task<Stream?> OpenReadAsync(StoredFileReference file, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(_options.AzureBlobConnectionString))
        {
            throw new InvalidOperationException("Storage:AzureBlobConnectionString no está configurado.");
        }

        var client = new BlobContainerClient(_options.AzureBlobConnectionString, file.Container);
        var blobClient = client.GetBlobClient(file.Path);
        var exists = await blobClient.ExistsAsync(cancellationToken);
        if (!exists.Value)
        {
            return null;
        }

        var response = await blobClient.DownloadStreamingAsync(cancellationToken: cancellationToken);
        return response.Value.Content;
    }
}
