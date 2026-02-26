namespace Accounting.Api.Storage;

public interface IFileStorage
{
    string ProviderName { get; }

    Task<StoredFileReference> SaveAsync(
        string container,
        string path,
        Stream content,
        string contentType,
        CancellationToken cancellationToken = default);

    Task<Stream?> OpenReadAsync(StoredFileReference file, CancellationToken cancellationToken = default);
}
