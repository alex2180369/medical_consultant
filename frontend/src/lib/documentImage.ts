/** Client-side helpers for document image preview and rotation before upload. */

const ROTATABLE_MIME = /^image\/(jpeg|png|webp)$/i;
const ROTATABLE_EXT = /\.(jpe?g|png|webp)$/i;

export function isRotatableImageFile(file: File): boolean {
  return ROTATABLE_MIME.test(file.type) || ROTATABLE_EXT.test(file.name);
}

function resolveOutputFormat(file: File): {
  mimeType: string;
  quality: number | undefined;
  filename: string;
} {
  const lowerName = file.name.toLowerCase();
  if (file.type === "image/png" || lowerName.endsWith(".png")) {
    return {
      mimeType: "image/png",
      quality: undefined,
      filename: lowerName.endsWith(".png") ? file.name : `${file.name}.png`
    };
  }

  const baseName = file.name.replace(/\.(webp|jpe?g)$/i, "") || "document";
  return {
    mimeType: "image/jpeg",
    quality: 0.92,
    filename: `${baseName}.jpg`
  };
}

async function canvasToFile(
  canvas: HTMLCanvasElement,
  file: File
): Promise<File> {
  const { mimeType, quality, filename } = resolveOutputFormat(file);

  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (result) => {
        if (result) {
          resolve(result);
          return;
        }
        reject(new Error("Не удалось подготовить изображение."));
      },
      mimeType,
      quality
    );
  });

  return new File([blob], filename, {
    type: mimeType,
    lastModified: Date.now()
  });
}

/**
 * Bake EXIF orientation into pixels so OCR sees an upright image.
 */
export async function normalizeImageOrientation(file: File): Promise<File> {
  if (!isRotatableImageFile(file)) {
    return file;
  }

  const bitmap = await createImageBitmap(file, {
    imageOrientation: "from-image"
  });
  try {
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d");
    if (!context) {
      return file;
    }
    context.drawImage(bitmap, 0, 0);
    return await canvasToFile(canvas, file);
  } finally {
    bitmap.close();
  }
}

/**
 * Rotate image by 90° steps. Positive quarterTurns = clockwise.
 */
export async function rotateImageFile(
  file: File,
  quarterTurns: 1 | -1
): Promise<File> {
  if (!isRotatableImageFile(file)) {
    throw new Error("Поворот доступен только для JPG, PNG и WEBP.");
  }

  const bitmap = await createImageBitmap(file, {
    imageOrientation: "from-image"
  });
  try {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("Canvas недоступен в этом браузере.");
    }

    if (quarterTurns === 1) {
      canvas.width = bitmap.height;
      canvas.height = bitmap.width;
      context.translate(canvas.width, 0);
      context.rotate(Math.PI / 2);
    } else {
      canvas.width = bitmap.height;
      canvas.height = bitmap.width;
      context.translate(0, canvas.height);
      context.rotate(-Math.PI / 2);
    }

    context.drawImage(bitmap, 0, 0);
    return await canvasToFile(canvas, file);
  } finally {
    bitmap.close();
  }
}
