"""Mocked botot3 client """


def client(*args, **kwargs):
    """
    Fake boto3.client implementation that returns a FakeS3Client.
    Mimics the behavior of the real boto3.client but without making any actual API calls.
    """
    class FakeS3Client:  # pylint: disable=too-few-public-methods
        """
        A fake S3 client to mock boto3 client behavior.
        """
        def generate_presigned_url(self, *args, **kwargs):  # pylint: disable=no-self-use
            params = kwargs.get('Params', {})
            file_key = params.get('Key', 'default-file.csv')
            return f'http://fake-s3-url.com/signed-{file_key}'

    return FakeS3Client()
