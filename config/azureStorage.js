const { BlobServiceClient } = require('@azure/storage-blob');
const { v4: uuidv4 } = require('uuid');
const path = require('path');

const CONTAINER_NAME = process.env.AZURE_STORAGE_CONTAINER || 'shield-media';

let blobServiceClient;
let containerClient;

const initStorage = async () => {
  try {
    blobServiceClient = BlobServiceClient.fromConnectionString(
      process.env.AZURE_STORAGE_CONNECTION_STRING
    );
    containerClient = blobServiceClient.getContainerClient(CONTAINER_NAME);
    await containerClient.createIfNotExists({ access: 'blob' });
    console.log(`✅ Azure Blob Storage ready — container: ${CONTAINER_NAME}`);
  } catch (error) {
    console.error('⚠️  Azure Storage init error:', error.message);
  }
};

const uploadBuffer = async (buffer, originalName, mimeType) => {
  if (!containerClient) throw new Error('Storage not initialized');
  const ext = path.extname(originalName) || '.jpg';
  const blobName = `products/${uuidv4()}${ext}`;
  const blockBlobClient = containerClient.getBlockBlobClient(blobName);
  await blockBlobClient.uploadData(buffer, {
    blobHTTPHeaders: { blobContentType: mimeType }
  });
  return blockBlobClient.url;
};

const deleteBlob = async (blobUrl) => {
  try {
    if (!containerClient || !blobUrl) return;
    const url = new URL(blobUrl);
    const blobName = url.pathname.replace(`/${CONTAINER_NAME}/`, '');
    const blockBlobClient = containerClient.getBlockBlobClient(blobName);
    await blockBlobClient.deleteIfExists();
  } catch (e) {
    console.error('Delete blob error:', e.message);
  }
};

module.exports = { initStorage, uploadBuffer, deleteBlob };
