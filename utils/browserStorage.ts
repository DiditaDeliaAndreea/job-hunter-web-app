const CV_DATABASE_NAME = 'careermatch-files';
const CV_STORE_NAME = 'cvs';

function openCvDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(CV_DATABASE_NAME, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(CV_STORE_NAME, { keyPath: 'name' });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('Could not open CV storage.'));
  });
}

export async function saveUploadedCvs(files: File[]): Promise<void> {
  if (typeof indexedDB === 'undefined' || files.length === 0) return;

  const database = await openCvDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(CV_STORE_NAME, 'readwrite');
    const store = transaction.objectStore(CV_STORE_NAME);
    files.forEach((file) => store.put({ name: file.name, file }));
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error('Could not save CV files.'));
  });
  database.close();
}

export async function getUploadedCv(name: string): Promise<File | null> {
  if (typeof indexedDB === 'undefined' || !name) return null;

  const database = await openCvDatabase();
  const file = await new Promise<File | null>((resolve, reject) => {
    const request = database.transaction(CV_STORE_NAME, 'readonly').objectStore(CV_STORE_NAME).get(name);
    request.onsuccess = () => resolve(request.result?.file || null);
    request.onerror = () => reject(request.error || new Error('Could not load CV file.'));
  });
  database.close();
  return file;
}

export async function renameUploadedCv(oldName: string, newName: string): Promise<void> {
  if (typeof indexedDB === 'undefined' || !oldName || !newName || oldName === newName) return;

  const database = await openCvDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(CV_STORE_NAME, 'readwrite');
    const store = transaction.objectStore(CV_STORE_NAME);
    const getRequest = store.get(oldName);
    getRequest.onsuccess = () => {
      const record = getRequest.result;
      if (!record) { resolve(); return; }
      const renamedFile = new File([record.file], newName, { type: record.file.type });
      store.delete(oldName);
      store.put({ name: newName, file: renamedFile });
    };
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error('Could not rename CV in storage.'));
  });
  database.close();
}
