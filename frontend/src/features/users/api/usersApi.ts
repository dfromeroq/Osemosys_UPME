/**
 * API de usuarios. Obtener usuario actual (/me), listar, crear, actualizar permisos
 * (catalog manager, official data importer, user manager).
 */
import { httpClient } from "@/shared/api/httpClient";
import type { User } from "@/types/domain";

type CatalogManagerUpdatePayload = {
  can_manage_catalogs: boolean;
};

type OfficialDataImportPermissionPayload = {
  can_import_official_data: boolean;
};

type UserPermissionsPayload = {
  is_active: boolean;
  can_manage_catalogs: boolean;
  can_import_official_data: boolean;
  can_manage_users: boolean;
  can_manage_scenarios: boolean;
  is_admin_reports?: boolean;
  can_manage_system_settings?: boolean;
};

type UserCreatePayload = {
  email: string;
  username: string;
  password: string;
  is_active: boolean;
  can_manage_catalogs: boolean;
  can_import_official_data: boolean;
  can_manage_users: boolean;
  can_manage_scenarios?: boolean;
  is_admin_reports?: boolean;
  can_manage_system_settings?: boolean;
};

/** Obtiene el usuario autenticado actual (requiere token válido) */
async function getMe(): Promise<User> {
  const { data } = await httpClient.get<User>("/users/me");
  return data;
}

async function setCatalogManager(userId: string, payload: CatalogManagerUpdatePayload): Promise<User> {
  const { data } = await httpClient.patch<User>(`/users/${userId}/catalog-manager`, payload);
  return data;
}

async function setOfficialDataImporter(userId: string, payload: OfficialDataImportPermissionPayload): Promise<User> {
  const { data } = await httpClient.patch<User>(`/users/${userId}/official-data-importer`, payload);
  return data;
}

async function listUsers(): Promise<User[]> {
  const { data } = await httpClient.get<User[]>("/users");
  return data;
}

async function createUser(payload: UserCreatePayload): Promise<User> {
  const { data } = await httpClient.post<User>("/users", payload);
  return data;
}

async function setPermissions(userId: string, payload: UserPermissionsPayload): Promise<User> {
  const { data } = await httpClient.patch<User>(`/users/${userId}/permissions`, payload);
  return data;
}

async function resetPassword(userId: string, newPassword: string): Promise<User> {
  const { data } = await httpClient.post<User>(`/users/${userId}/reset-password`, {
    new_password: newPassword,
  });
  return data;
}

export const usersApi = {
  getMe,
  listUsers,
  createUser,
  setPermissions,
  setCatalogManager,
  setOfficialDataImporter,
  resetPassword,
};

