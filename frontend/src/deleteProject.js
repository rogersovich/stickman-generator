import { api } from "./api.js";

// Asks for confirmation in a modal, deletes the project, returns true when deleted.
// `dialog` comes from useDialog().
export async function confirmDelete(project, dialog) {
  const images = project.done_count ?? project.scenes?.filter((s) => s.image_file).length ?? 0;
  const ok = await dialog.confirm({
    title: `Hapus project "${project.title}"?`,
    message: `${images} gambar dan semua datanya di folder output akan dihapus permanen. Tidak bisa dibatalkan.`,
    confirmLabel: "Hapus permanen",
    danger: true,
  });
  if (!ok) return false;
  try {
    await api.deleteProject(project.id);
    return true;
  } catch (e) {
    await dialog.alert({ title: "Gagal menghapus project", message: e.message });
    return false;
  }
}
