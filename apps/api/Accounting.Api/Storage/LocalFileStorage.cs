using Microsoft.Extensions.Options;

namespace Accounting.Api.Storage;

public sealed class LocalFileStorage(IOptions<StorageOptions> options) : IFileStorage
{
    private readonly StorageOptions _options = options.Value;

    public string ProviderName => "Local";

    public async Task<StoredFileReference> SaveAsync(
        string container,
        string path,
        Stream content,
        string contentType,
        CancellationToken cancellationToken = default)
    {
        var basePath = Path.Combine(_options.LocalRootPath, container);
        var fullPath = Path.Combine(basePath, path.Replace('/', Path.DirectorySeparatorChar));
        var directory = Path.GetDirectoryName(fullPath);

        if (!string.IsNullOrWhiteSpace(directory))
        {
            Directory.CreateDirectory(directory);
        }

        await using var output = File.Create(fullPath);
        await content.CopyToAsync(output, cancellationToken);

        return new StoredFileReference(ProviderName, container, path);
    }

    public Task<Stream?> OpenReadAsync(StoredFileReference file, CancellationToken cancellationToken = default)
    {
        var fullPath = Path.Combine(_options.LocalRootPath, file.Container, file.Path.Replace('/', Path.DirectorySeparatorChar));
        if (!File.Exists(fullPath))
        {
            return Task.FromResult<Stream?>(null);
        }

        Stream stream = File.OpenRead(fullPath);
        return Task.FromResult<Stream?>(stream);
    }
}
