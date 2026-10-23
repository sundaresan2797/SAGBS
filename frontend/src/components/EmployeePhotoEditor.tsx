import { Camera, Save, Trash2, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/EntityCard";
import { Sheet } from "@/components/ui/Sheet";
import { usePhotos } from "@/hooks/usePhotos";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage } from "@/services/api";
import { photoService } from "@/services/photoService";

// The server enforces the real limit (PHOTO_MAX_UPLOAD_MB); this only saves a pointless upload.
const MAX_MB = 5;
const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];

/**
 * A person's photo with "Change photo" / "Remove photo" - for yourself, or (HR, Founder, Admin) for anyone.
 * A picked picture is previewed as a round crop before saving; the server crops it to the same centre square.
 */
export function EmployeePhotoEditor({ employeeId, name, canEdit }: { employeeId: number; name: string; canEdit: boolean }) {
  const { versions, refresh } = usePhotos();
  const { showToast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewBroken, setPreviewBroken] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isRemoving, setIsRemoving] = useState(false);
  const hasPhoto = Boolean(versions[employeeId]);

  useEffect(() => {
    setPreviewBroken(false);
    if (!picked) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(picked);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [picked]);

  const choose = (file: File | undefined) => {
    if (inputRef.current) inputRef.current.value = ""; // so choosing the same file again still fires
    if (!file) return;
    setFormError(null);
    if (!ACCEPTED.includes(file.type)) {
      setFormError("Please choose a JPG, PNG or WebP picture.");
    } else if (file.size > MAX_MB * 1024 * 1024) {
      setFormError(`That picture is larger than ${MAX_MB} MB. Please choose a smaller one.`);
    }
    setPicked(file);
  };

  const closeSheet = () => {
    setPicked(null);
    setFormError(null);
  };

  const save = async () => {
    if (!picked || formError) return;
    setIsSaving(true);
    try {
      await photoService.upload(employeeId, picked);
      await refresh();
      showToast("Photo saved", "success");
      closeSheet();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const remove = async () => {
    setIsRemoving(true);
    try {
      await photoService.remove(employeeId);
      await refresh();
      showToast("Photo removed", "success");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setIsRemoving(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-2">
      <Avatar name={name} size="xl" employeeId={employeeId} />
      {canEdit && (
        <>
          <input
            ref={inputRef}
            id={`photo_input_${employeeId}`}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            onChange={(e) => choose(e.target.files?.[0])}
          />
          <div className="flex flex-wrap justify-center gap-1">
            <Button variant="ghost" size="sm" icon={<Camera className="h-4 w-4" />} onClick={() => inputRef.current?.click()}>
              {hasPhoto ? "Change photo" : "Add photo"}
            </Button>
            {hasPhoto && (
              <Button variant="ghost" size="sm" isLoading={isRemoving} icon={<Trash2 className="h-4 w-4" />} onClick={remove}>
                Remove
              </Button>
            )}
          </div>
        </>
      )}

      <Sheet
        title="Use this photo?"
        isOpen={picked !== null}
        onClose={closeSheet}
        footer={
          <>
            <Button variant="secondary" size="lg" onClick={closeSheet}>Not now</Button>
            <Button size="lg" isLoading={isSaving} disabled={Boolean(formError) || previewBroken} onClick={save} icon={<Save className="h-5 w-5" />}>
              Save photo
            </Button>
          </>
        }
      >
        <div className="flex flex-col items-center gap-4">
          {previewUrl && !previewBroken && (
            <img
              src={previewUrl}
              alt={`Preview of the new photo for ${name}`}
              className="h-40 w-40 rounded-3xl object-cover shadow-md"
              onError={() => setPreviewBroken(true)}
            />
          )}
          <p className="text-center text-base text-stone-600">
            The middle of your picture is used, as a square. Faces in the centre look best.
          </p>
          {previewBroken && !formError && (
            <p role="alert" className="text-center text-base font-medium text-rose-800">
              This file can't be shown as a picture. Please choose a JPG, PNG or WebP picture.
            </p>
          )}
          {formError && (
            <div role="alert" className="flex w-full items-start gap-2 rounded-xl bg-rose-50 p-3 text-base font-medium text-rose-800">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
              {formError}
            </div>
          )}
        </div>
      </Sheet>
    </div>
  );
}
