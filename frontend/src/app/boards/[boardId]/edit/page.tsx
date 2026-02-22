"use client";

export const dynamic = "force-dynamic";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

import { useAuth } from "@/auth/clerk";
import { X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/mutator";
import {
  type getBoardApiV1BoardsBoardIdGetResponse,
  useGetBoardApiV1BoardsBoardIdGet,
  useUpdateBoardApiV1BoardsBoardIdPatch,
} from "@/api/generated/boards/boards";
import {
  type listAgentsApiV1AgentsGetResponse,
  useListAgentsApiV1AgentsGet,
} from "@/api/generated/agents/agents";
import {
  getListBoardWebhooksApiV1BoardsBoardIdWebhooksGetQueryKey,
  type listBoardWebhooksApiV1BoardsBoardIdWebhooksGetResponse,
  useCreateBoardWebhookApiV1BoardsBoardIdWebhooksPost,
  useDeleteBoardWebhookApiV1BoardsBoardIdWebhooksWebhookIdDelete,
  useListBoardWebhooksApiV1BoardsBoardIdWebhooksGet,
  useUpdateBoardWebhookApiV1BoardsBoardIdWebhooksWebhookIdPatch,
} from "@/api/generated/board-webhooks/board-webhooks";
import {
  type listBoardGroupsApiV1BoardGroupsGetResponse,
  useListBoardGroupsApiV1BoardGroupsGet,
} from "@/api/generated/board-groups/board-groups";
import {
  type listBoardsApiV1BoardsGetResponse,
  useListBoardsApiV1BoardsGet,
} from "@/api/generated/boards/boards";
import {
  type listGatewaysApiV1GatewaysGetResponse,
  useListGatewaysApiV1GatewaysGet,
} from "@/api/generated/gateways/gateways";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import type {
  AgentRead,
  BoardGroupRead,
  BoardWebhookRead,
  BoardRead,
  BoardUpdate,
} from "@/api/generated/model";
import { customFetch } from "@/api/mutator";
import { useQuery, useMutation } from "@tanstack/react-query";

type PipelineRead = {
  id: string;
  source_board_id: string;
  target_board_id: string;
  trigger_status: string;
  enabled: boolean;
  task_title_template: string;
  task_description_template: string | null;
  target_agent_id: string | null;
  transfer_files: boolean;
  notify_agent: boolean;
  notification_template: string | null;
  created_at: string;
  updated_at: string;
};
import { BoardOnboardingChat } from "@/components/BoardOnboardingChat";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import SearchableSelect from "@/components/ui/searchable-select";
import { Textarea } from "@/components/ui/textarea";
import { localDateInputToUtcIso, toLocalDateInput } from "@/lib/datetime";
import { Markdown } from "@/components/atoms/Markdown";

const slugify = (value: string) =>
  value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "") || "board";

const LEAD_AGENT_VALUE = "__lead_agent__";

type WebhookCardProps = {
  webhook: BoardWebhookRead;
  agents: AgentRead[];
  isLoading: boolean;
  isWebhookCreating: boolean;
  isDeletingWebhook: boolean;
  isUpdatingWebhook: boolean;
  copiedWebhookId: string | null;
  onCopy: (webhook: BoardWebhookRead) => void;
  onDelete: (webhookId: string) => void;
  onViewPayloads: (webhookId: string) => void;
  onUpdate: (
    webhookId: string,
    description: string,
    agentId: string | null,
  ) => Promise<boolean>;
};

function WebhookCard({
  webhook,
  agents,
  isLoading,
  isWebhookCreating,
  isDeletingWebhook,
  isUpdatingWebhook,
  copiedWebhookId,
  onCopy,
  onDelete,
  onViewPayloads,
  onUpdate,
}: WebhookCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draftDescription, setDraftDescription] = useState(webhook.description);
  const [draftAgentValue, setDraftAgentValue] = useState(
    webhook.agent_id ?? LEAD_AGENT_VALUE,
  );

  const isBusy =
    isLoading || isWebhookCreating || isDeletingWebhook || isUpdatingWebhook;
  const trimmedDescription = draftDescription.trim();
  const isDescriptionChanged =
    trimmedDescription !== webhook.description.trim();
  const isAgentChanged =
    draftAgentValue !== (webhook.agent_id ?? LEAD_AGENT_VALUE);
  const isChanged = isDescriptionChanged || isAgentChanged;
  const mappedAgent = webhook.agent_id
    ? (agents.find((agent) => agent.id === webhook.agent_id) ?? null)
    : null;

  const handleSave = async () => {
    if (!trimmedDescription) return;
    if (!isChanged) {
      setIsEditing(false);
      return;
    }
    const saved = await onUpdate(
      webhook.id,
      trimmedDescription,
      draftAgentValue === LEAD_AGENT_VALUE ? null : draftAgentValue,
    );
    if (saved) {
      setIsEditing(false);
    }
  };

  return (
    <div
      key={webhook.id}
      className="space-y-3 rounded-lg border border-slate-200 px-4 py-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-slate-900">
          Webhook {webhook.id.slice(0, 8)}
        </span>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => onCopy(webhook)}
            disabled={isBusy}
          >
            {copiedWebhookId === webhook.id ? "Copied" : "Copy endpoint"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => onViewPayloads(webhook.id)}
            disabled={isBusy}
          >
            View payloads
          </Button>
          {isEditing ? (
            <>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setDraftDescription(webhook.description);
                  setDraftAgentValue(webhook.agent_id ?? LEAD_AGENT_VALUE);
                  setIsEditing(false);
                }}
                disabled={isBusy}
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={handleSave}
                disabled={isBusy || !trimmedDescription}
              >
                {isUpdatingWebhook ? "Saving…" : "Save"}
              </Button>
            </>
          ) : (
            <>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setDraftDescription(webhook.description);
                  setDraftAgentValue(webhook.agent_id ?? LEAD_AGENT_VALUE);
                  setIsEditing(true);
                }}
                disabled={isBusy}
              >
                Edit
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => onDelete(webhook.id)}
                disabled={isBusy}
              >
                {isDeletingWebhook ? "Deleting…" : "Delete"}
              </Button>
            </>
          )}
        </div>
      </div>
      {isEditing ? (
        <>
          <Textarea
            value={draftDescription}
            onChange={(event) => setDraftDescription(event.target.value)}
            placeholder="Describe exactly what the lead agent should do when payloads arrive."
            className="min-h-[90px]"
            disabled={isBusy}
          />
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-900">Agent</label>
            <Select
              value={draftAgentValue}
              onValueChange={setDraftAgentValue}
              disabled={isBusy}
            >
              <SelectTrigger>
                <SelectValue placeholder="Lead agent (default fallback)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={LEAD_AGENT_VALUE}>
                  Lead agent (default fallback)
                </SelectItem>
                {agents.map((agent) => (
                  <SelectItem key={agent.id} value={agent.id}>
                    {agent.name}
                    {agent.is_board_lead ? " (lead)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </>
      ) : (
        <>
          <div className="text-sm text-slate-700">
            <Markdown
              content={webhook.description || ""}
              variant="description"
            />
          </div>
          <p className="text-xs text-slate-600">
            Recipient: {mappedAgent?.name ?? "Lead agent"}
          </p>
        </>
      )}
      <div className="rounded-md bg-slate-50 px-3 py-2">
        <code className="break-all text-xs text-slate-700">
          {webhook.endpoint_url ?? webhook.endpoint_path}
        </code>
      </div>
    </div>
  );
}

export default function EditBoardPage() {
  const { isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const params = useParams();
  const boardIdParam = params?.boardId;
  const boardId = Array.isArray(boardIdParam) ? boardIdParam[0] : boardIdParam;

  const { isAdmin } = useOrganizationMembership(isSignedIn);

  const mainRef = useRef<HTMLElement | null>(null);

  const [board, setBoard] = useState<BoardRead | null>(null);
  const [name, setName] = useState<string | undefined>(undefined);
  const [description, setDescription] = useState<string | undefined>(undefined);
  const [gatewayId, setGatewayId] = useState<string | undefined>(undefined);
  const [boardGroupId, setBoardGroupId] = useState<string | undefined>(
    undefined,
  );
  const [boardType, setBoardType] = useState<string | undefined>(undefined);
  const [objective, setObjective] = useState<string | undefined>(undefined);
  const [requireApprovalForDone, setRequireApprovalForDone] = useState<
    boolean | undefined
  >(undefined);
  const [requireReviewBeforeDone, setRequireReviewBeforeDone] = useState<
    boolean | undefined
  >(undefined);
  const [
    blockStatusChangesWithPendingApproval,
    setBlockStatusChangesWithPendingApproval,
  ] = useState<boolean | undefined>(undefined);
  const [onlyLeadCanChangeStatus, setOnlyLeadCanChangeStatus] = useState<
    boolean | undefined
  >(undefined);
  const [maxAgents, setMaxAgents] = useState<number | undefined>(undefined);
  const [successMetrics, setSuccessMetrics] = useState<string | undefined>(
    undefined,
  );
  const [targetDate, setTargetDate] = useState<string | undefined>(undefined);

  const [error, setError] = useState<string | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [webhookDescription, setWebhookDescription] = useState("");
  const [webhookAgentValue, setWebhookAgentValue] = useState(LEAD_AGENT_VALUE);
  const [webhookError, setWebhookError] = useState<string | null>(null);
  const [copiedWebhookId, setCopiedWebhookId] = useState<string | null>(null);

  const onboardingParam = searchParams.get("onboarding");
  const searchParamsString = searchParams.toString();
  const shouldAutoOpenOnboarding =
    onboardingParam !== null &&
    onboardingParam !== "" &&
    onboardingParam !== "0" &&
    onboardingParam.toLowerCase() !== "false";

  const [isOnboardingOpen, setIsOnboardingOpen] = useState(
    shouldAutoOpenOnboarding,
  );

  useEffect(() => {
    if (!isOnboardingOpen) return;

    const mainEl = mainRef.current;
    const previousMainOverflow = mainEl?.style.overflow ?? "";
    const previousHtmlOverflow = document.documentElement.style.overflow;
    const previousBodyOverflow = document.body.style.overflow;

    if (mainEl) {
      mainEl.style.overflow = "hidden";
    }
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";

    return () => {
      if (mainEl) {
        mainEl.style.overflow = previousMainOverflow;
      }
      document.documentElement.style.overflow = previousHtmlOverflow;
      document.body.style.overflow = previousBodyOverflow;
    };
  }, [isOnboardingOpen]);

  useEffect(() => {
    if (!boardId) return;
    if (!shouldAutoOpenOnboarding) return;

    // Remove the flag from the URL so refreshes don't constantly reopen it.
    const nextParams = new URLSearchParams(searchParamsString);
    nextParams.delete("onboarding");
    const qs = nextParams.toString();
    router.replace(
      qs ? `/boards/${boardId}/edit?${qs}` : `/boards/${boardId}/edit`,
    );
  }, [boardId, router, searchParamsString, shouldAutoOpenOnboarding]);

  const gatewaysQuery = useListGatewaysApiV1GatewaysGet<
    listGatewaysApiV1GatewaysGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchOnMount: "always",
      retry: false,
    },
  });

  const groupsQuery = useListBoardGroupsApiV1BoardGroupsGet<
    listBoardGroupsApiV1BoardGroupsGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchOnMount: "always",
      retry: false,
    },
  });

  const boardQuery = useGetBoardApiV1BoardsBoardIdGet<
    getBoardApiV1BoardsBoardIdGetResponse,
    ApiError
  >(boardId ?? "", {
    query: {
      enabled: Boolean(isSignedIn && isAdmin && boardId),
      refetchOnMount: "always",
      retry: false,
    },
  });
  const webhooksQuery = useListBoardWebhooksApiV1BoardsBoardIdWebhooksGet<
    listBoardWebhooksApiV1BoardsBoardIdWebhooksGetResponse,
    ApiError
  >(
    boardId ?? "",
    { limit: 50 },
    {
      query: {
        enabled: Boolean(isSignedIn && isAdmin && boardId),
        refetchOnMount: "always",
        retry: false,
      },
    },
  );
  const agentsQuery = useListAgentsApiV1AgentsGet<
    listAgentsApiV1AgentsGetResponse,
    ApiError
  >(
    { board_id: boardId ?? null, limit: 200 },
    {
      query: {
        enabled: Boolean(isSignedIn && isAdmin && boardId),
        refetchOnMount: "always",
        retry: false,
      },
    },
  );

  const updateBoardMutation = useUpdateBoardApiV1BoardsBoardIdPatch<ApiError>({
    mutation: {
      onSuccess: (result) => {
        if (result.status === 200) {
          router.push(`/boards/${result.data.id}`);
        }
      },
      onError: (err) => {
        setError(err.message || "Something went wrong.");
      },
    },
  });
  const createWebhookMutation =
    useCreateBoardWebhookApiV1BoardsBoardIdWebhooksPost<ApiError>({
      mutation: {
        onSuccess: async () => {
          if (!boardId) return;
          setWebhookDescription("");
          setWebhookAgentValue(LEAD_AGENT_VALUE);
          await queryClient.invalidateQueries({
            queryKey:
              getListBoardWebhooksApiV1BoardsBoardIdWebhooksGetQueryKey(
                boardId,
              ),
          });
        },
        onError: (err) => {
          setWebhookError(err.message || "Unable to create webhook.");
        },
      },
    });
  const deleteWebhookMutation =
    useDeleteBoardWebhookApiV1BoardsBoardIdWebhooksWebhookIdDelete<ApiError>({
      mutation: {
        onSuccess: async () => {
          if (!boardId) return;
          await queryClient.invalidateQueries({
            queryKey:
              getListBoardWebhooksApiV1BoardsBoardIdWebhooksGetQueryKey(
                boardId,
              ),
          });
        },
        onError: (err) => {
          setWebhookError(err.message || "Unable to delete webhook.");
        },
      },
    });
  const updateWebhookMutation =
    useUpdateBoardWebhookApiV1BoardsBoardIdWebhooksWebhookIdPatch<ApiError>({
      mutation: {
        onSuccess: async () => {
          if (!boardId) return;
          await queryClient.invalidateQueries({
            queryKey:
              getListBoardWebhooksApiV1BoardsBoardIdWebhooksGetQueryKey(
                boardId,
              ),
          });
        },
        onError: (err) => {
          setWebhookError(err.message || "Unable to update webhook.");
        },
      },
    });

  const gateways = useMemo(() => {
    if (gatewaysQuery.data?.status !== 200) return [];
    return gatewaysQuery.data.data.items ?? [];
  }, [gatewaysQuery.data]);
  const loadedBoard: BoardRead | null =
    boardQuery.data?.status === 200 ? boardQuery.data.data : null;
  const baseBoard = board ?? loadedBoard;

  const resolvedName = name ?? baseBoard?.name ?? "";
  const resolvedDescription = description ?? baseBoard?.description ?? "";
  const resolvedGatewayId = gatewayId ?? baseBoard?.gateway_id ?? "";
  const resolvedBoardGroupId =
    boardGroupId ?? baseBoard?.board_group_id ?? "none";
  const resolvedBoardType = boardType ?? baseBoard?.board_type ?? "goal";
  const resolvedObjective = objective ?? baseBoard?.objective ?? "";
  const resolvedRequireApprovalForDone =
    requireApprovalForDone ?? baseBoard?.require_approval_for_done ?? true;
  const resolvedRequireReviewBeforeDone =
    requireReviewBeforeDone ?? baseBoard?.require_review_before_done ?? false;
  const resolvedBlockStatusChangesWithPendingApproval =
    blockStatusChangesWithPendingApproval ??
    baseBoard?.block_status_changes_with_pending_approval ??
    false;
  const resolvedOnlyLeadCanChangeStatus =
    onlyLeadCanChangeStatus ?? baseBoard?.only_lead_can_change_status ?? false;
  const resolvedMaxAgents = maxAgents ?? baseBoard?.max_agents ?? 1;
  const resolvedSuccessMetrics =
    successMetrics ??
    (baseBoard?.success_metrics
      ? JSON.stringify(baseBoard.success_metrics, null, 2)
      : "");
  const resolvedTargetDate =
    targetDate ?? toLocalDateInput(baseBoard?.target_date);

  const displayGatewayId = resolvedGatewayId || gateways[0]?.id || "";
  const isWebhookCreating = createWebhookMutation.isPending;
  const deletingWebhookId =
    deleteWebhookMutation.isPending && deleteWebhookMutation.variables
      ? deleteWebhookMutation.variables.webhookId
      : null;
  const updatingWebhookId =
    updateWebhookMutation.isPending && updateWebhookMutation.variables
      ? updateWebhookMutation.variables.webhookId
      : null;
  const isWebhookBusy =
    isWebhookCreating ||
    deleteWebhookMutation.isPending ||
    updateWebhookMutation.isPending;

  const isLoading =
    gatewaysQuery.isLoading ||
    groupsQuery.isLoading ||
    boardQuery.isLoading ||
    updateBoardMutation.isPending;
  const errorMessage =
    error ??
    gatewaysQuery.error?.message ??
    groupsQuery.error?.message ??
    boardQuery.error?.message ??
    null;
  const webhookErrorMessage =
    webhookError ??
    webhooksQuery.error?.message ??
    agentsQuery.error?.message ??
    null;

  const isFormReady = Boolean(
    resolvedName.trim() && resolvedDescription.trim() && displayGatewayId,
  );

  const gatewayOptions = useMemo(
    () =>
      gateways.map((gateway) => ({ value: gateway.id, label: gateway.name })),
    [gateways],
  );

  const groups = useMemo<BoardGroupRead[]>(() => {
    if (groupsQuery.data?.status !== 200) return [];
    return groupsQuery.data.data.items ?? [];
  }, [groupsQuery.data]);
  const groupOptions = useMemo(
    () => [
      { value: "none", label: "No group" },
      ...groups.map((group) => ({ value: group.id, label: group.name })),
    ],
    [groups],
  );
  const webhookAgents = useMemo<AgentRead[]>(() => {
    if (agentsQuery.data?.status !== 200) return [];
    return agentsQuery.data.data.items ?? [];
  }, [agentsQuery.data]);
  const webhooks = useMemo<BoardWebhookRead[]>(() => {
    if (webhooksQuery.data?.status !== 200) return [];
    return webhooksQuery.data.data.items ?? [];
  }, [webhooksQuery.data]);

  // --- Pipeline state ---
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineTargetBoardId, setPipelineTargetBoardId] = useState("");
  const [pipelineTriggerStatus, setPipelineTriggerStatus] = useState("done");
  const [pipelineTitleTemplate, setPipelineTitleTemplate] = useState("");
  const [pipelineDescriptionTemplate, setPipelineDescriptionTemplate] =
    useState("");
  const [pipelineTargetAgentId, setPipelineTargetAgentId] =
    useState(LEAD_AGENT_VALUE);
  const [pipelineTransferFiles, setPipelineTransferFiles] = useState(false);
  const [pipelineNotifyAgent, setPipelineNotifyAgent] = useState(false);
  const [pipelineNotificationTemplate, setPipelineNotificationTemplate] =
    useState("");
  const [editingPipelineId, setEditingPipelineId] = useState<string | null>(
    null,
  );
  const [editPipelineData, setEditPipelineData] = useState<{
    target_board_id: string;
    trigger_status: string;
    task_title_template: string;
    task_description_template: string;
    target_agent_id: string;
    transfer_files: boolean;
    notify_agent: boolean;
    notification_template: string;
  } | null>(null);

  const allBoardsQuery = useListBoardsApiV1BoardsGet<
    listBoardsApiV1BoardsGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchOnMount: "always",
      retry: false,
    },
  });
  const allBoards = useMemo<BoardRead[]>(() => {
    if (allBoardsQuery.data?.status !== 200) return [];
    return allBoardsQuery.data.data.items ?? [];
  }, [allBoardsQuery.data]);

  const pipelinesQuery = useQuery<PipelineRead[]>({
    queryKey: ["board-pipelines", boardId],
    queryFn: async () => {
      const res = await customFetch<{ data: PipelineRead[]; status: number }>(
        `/api/v1/boards/${boardId}/pipelines`,
        { method: "GET" },
      );
      return res.data;
    },
    enabled: Boolean(isSignedIn && isAdmin && boardId),
    refetchOnMount: true,
    retry: false,
  });
  const pipelines = pipelinesQuery.data ?? [];

  const createPipelineMutation = useMutation({
    mutationFn: async (data: {
      target_board_id: string;
      trigger_status: string;
      task_title_template: string;
      task_description_template: string | null;
      target_agent_id: string | null;
      enabled: boolean;
      transfer_files: boolean;
      notify_agent: boolean;
      notification_template: string | null;
    }) => {
      return customFetch<{ data: PipelineRead; status: number }>(
        `/api/v1/boards/${boardId}/pipelines`,
        { method: "POST", body: JSON.stringify(data) },
      );
    },
    onSuccess: () => {
      setPipelineTitleTemplate("");
      setPipelineDescriptionTemplate("");
      setPipelineTargetBoardId("");
      setPipelineTriggerStatus("done");
      setPipelineTargetAgentId(LEAD_AGENT_VALUE);
      setPipelineTransferFiles(false);
      setPipelineNotifyAgent(false);
      setPipelineNotificationTemplate("");
      pipelinesQuery.refetch();
    },
    onError: (err: Error) => {
      setPipelineError(err.message || "Unable to create pipeline.");
    },
  });

  const deletePipelineMutation = useMutation({
    mutationFn: async (pipelineId: string) => {
      return customFetch<{ status: number }>(
        `/api/v1/boards/${boardId}/pipelines/${pipelineId}`,
        { method: "DELETE" },
      );
    },
    onSuccess: () => {
      pipelinesQuery.refetch();
    },
    onError: (err: Error) => {
      setPipelineError(err.message || "Unable to delete pipeline.");
    },
  });

  const togglePipelineMutation = useMutation({
    mutationFn: async ({
      pipelineId,
      enabled,
    }: {
      pipelineId: string;
      enabled: boolean;
    }) => {
      return customFetch<{ data: PipelineRead; status: number }>(
        `/api/v1/boards/${boardId}/pipelines/${pipelineId}`,
        { method: "PATCH", body: JSON.stringify({ enabled }) },
      );
    },
    onSuccess: () => {
      pipelinesQuery.refetch();
    },
    onError: (err: Error) => {
      setPipelineError(err.message || "Unable to update pipeline.");
    },
  });

  const updatePipelineMutation = useMutation({
    mutationFn: async ({
      pipelineId,
      data,
    }: {
      pipelineId: string;
      data: {
        target_board_id?: string;
        trigger_status?: string;
        task_title_template?: string;
        task_description_template?: string | null;
        target_agent_id?: string | null;
        transfer_files?: boolean;
        notify_agent?: boolean;
        notification_template?: string | null;
      };
    }) => {
      return customFetch<{ data: PipelineRead; status: number }>(
        `/api/v1/boards/${boardId}/pipelines/${pipelineId}`,
        { method: "PATCH", body: JSON.stringify(data) },
      );
    },
    onSuccess: () => {
      setEditingPipelineId(null);
      setEditPipelineData(null);
      pipelinesQuery.refetch();
    },
    onError: (err: Error) => {
      setPipelineError(err.message || "Unable to update pipeline.");
    },
  });

  const handleCreatePipeline = () => {
    if (!boardId || !pipelineTargetBoardId) return;
    if (!pipelineTitleTemplate.trim()) {
      setPipelineError("Title template is required.");
      return;
    }
    setPipelineError(null);
    createPipelineMutation.mutate({
      target_board_id: pipelineTargetBoardId,
      trigger_status: pipelineTriggerStatus,
      task_title_template: pipelineTitleTemplate.trim(),
      task_description_template: pipelineDescriptionTemplate.trim() || null,
      target_agent_id:
        pipelineTargetAgentId === LEAD_AGENT_VALUE
          ? null
          : pipelineTargetAgentId,
      enabled: true,
      transfer_files: pipelineTransferFiles,
      notify_agent: pipelineNotifyAgent,
      notification_template: pipelineNotificationTemplate.trim() || null,
    });
  };

  const handleDeletePipeline = (pipelineId: string) => {
    if (deletePipelineMutation.isPending) return;
    setPipelineError(null);
    deletePipelineMutation.mutate(pipelineId);
  };

  const handleTogglePipeline = (pipelineId: string, enabled: boolean) => {
    if (togglePipelineMutation.isPending) return;
    setPipelineError(null);
    togglePipelineMutation.mutate({ pipelineId, enabled });
  };

  const handleStartEditPipeline = (pipeline: PipelineRead) => {
    setEditingPipelineId(pipeline.id);
    setEditPipelineData({
      target_board_id: pipeline.target_board_id,
      trigger_status: pipeline.trigger_status,
      task_title_template: pipeline.task_title_template,
      task_description_template: pipeline.task_description_template ?? "",
      target_agent_id: pipeline.target_agent_id ?? LEAD_AGENT_VALUE,
      transfer_files: pipeline.transfer_files,
      notify_agent: pipeline.notify_agent,
      notification_template: pipeline.notification_template ?? "",
    });
    setPipelineError(null);
  };

  const handleCancelEditPipeline = () => {
    setEditingPipelineId(null);
    setEditPipelineData(null);
  };

  const handleSaveEditPipeline = () => {
    if (!editingPipelineId || !editPipelineData) return;
    if (!editPipelineData.task_title_template.trim()) {
      setPipelineError("Title template is required.");
      return;
    }
    setPipelineError(null);
    updatePipelineMutation.mutate({
      pipelineId: editingPipelineId,
      data: {
        target_board_id: editPipelineData.target_board_id,
        trigger_status: editPipelineData.trigger_status,
        task_title_template: editPipelineData.task_title_template.trim(),
        task_description_template:
          editPipelineData.task_description_template.trim() || null,
        target_agent_id:
          editPipelineData.target_agent_id === LEAD_AGENT_VALUE
            ? null
            : editPipelineData.target_agent_id,
        transfer_files: editPipelineData.transfer_files,
        notify_agent: editPipelineData.notify_agent,
        notification_template:
          editPipelineData.notification_template.trim() || null,
      },
    });
  };

  const handleOnboardingConfirmed = (updated: BoardRead) => {
    setBoard(updated);
    setIsOnboardingOpen(false);
    router.push(`/boards/${updated.id}`);
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isSignedIn || !boardId) return;
    const trimmedName = resolvedName.trim();
    if (!trimmedName) {
      setError("Board name is required.");
      return;
    }
    const resolvedGatewayId = displayGatewayId;
    if (!resolvedGatewayId) {
      setError("Select a gateway before saving.");
      return;
    }
    const trimmedDescription = resolvedDescription.trim();
    if (!trimmedDescription) {
      setError("Board description is required.");
      return;
    }
    if (!Number.isInteger(resolvedMaxAgents) || resolvedMaxAgents < 0) {
      setError("Max worker agents must be a non-negative integer.");
      return;
    }

    setError(null);
    setMetricsError(null);

    let parsedMetrics: Record<string, unknown> | null = null;
    if (resolvedBoardType !== "general" && resolvedSuccessMetrics.trim()) {
      try {
        parsedMetrics = JSON.parse(resolvedSuccessMetrics) as Record<
          string,
          unknown
        >;
      } catch {
        setMetricsError("Success metrics must be valid JSON.");
        return;
      }
    }

    const payload: BoardUpdate = {
      name: trimmedName,
      slug: slugify(trimmedName),
      description: trimmedDescription,
      gateway_id: resolvedGatewayId || null,
      board_group_id:
        resolvedBoardGroupId === "none" ? null : resolvedBoardGroupId,
      board_type: resolvedBoardType,
      objective:
        resolvedBoardType === "general"
          ? null
          : resolvedObjective.trim() || null,
      require_approval_for_done: resolvedRequireApprovalForDone,
      require_review_before_done: resolvedRequireReviewBeforeDone,
      block_status_changes_with_pending_approval:
        resolvedBlockStatusChangesWithPendingApproval,
      only_lead_can_change_status: resolvedOnlyLeadCanChangeStatus,
      max_agents: resolvedMaxAgents,
      success_metrics: resolvedBoardType === "general" ? null : parsedMetrics,
      target_date:
        resolvedBoardType === "general"
          ? null
          : localDateInputToUtcIso(resolvedTargetDate),
    };

    updateBoardMutation.mutate({ boardId, data: payload });
  };

  const handleCreateWebhook = () => {
    if (!boardId) return;
    const trimmedDescription = webhookDescription.trim();
    if (!trimmedDescription) {
      setWebhookError("Webhook instruction is required.");
      return;
    }
    setWebhookError(null);
    const mappedAgentId =
      webhookAgentValue === LEAD_AGENT_VALUE ? null : webhookAgentValue;
    createWebhookMutation.mutate({
      boardId,
      data: {
        description: trimmedDescription,
        enabled: true,
        agent_id: mappedAgentId,
      },
    });
  };

  const handleDeleteWebhook = (webhookId: string) => {
    if (!boardId) return;
    if (deleteWebhookMutation.isPending) return;
    setWebhookError(null);
    deleteWebhookMutation.mutate({ boardId, webhookId });
  };

  const handleUpdateWebhook = async (
    webhookId: string,
    description: string,
    agentId: string | null,
  ): Promise<boolean> => {
    if (!boardId) return false;
    if (updateWebhookMutation.isPending) return false;
    const trimmedDescription = description.trim();
    if (!trimmedDescription) {
      setWebhookError("Webhook instruction is required.");
      return false;
    }
    setWebhookError(null);
    try {
      await updateWebhookMutation.mutateAsync({
        boardId,
        webhookId,
        data: {
          description: trimmedDescription,
          agent_id: agentId,
        },
      });
      return true;
    } catch {
      return false;
    }
  };

  const handleCopyWebhookEndpoint = async (webhook: BoardWebhookRead) => {
    const endpoint = (webhook.endpoint_url ?? webhook.endpoint_path).trim();
    try {
      await navigator.clipboard.writeText(endpoint);
      setCopiedWebhookId(webhook.id);
      window.setTimeout(() => {
        setCopiedWebhookId((current) =>
          current === webhook.id ? null : current,
        );
      }, 1500);
    } catch {
      setWebhookError("Unable to copy webhook endpoint.");
    }
  };

  const handleViewWebhookPayloads = (webhookId: string) => {
    if (!boardId) return;
    router.push(`/boards/${boardId}/webhooks/${webhookId}/payloads`);
  };

  return (
    <>
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to edit boards.",
          forceRedirectUrl: `/boards/${boardId}/edit`,
          signUpForceRedirectUrl: `/boards/${boardId}/edit`,
        }}
        title="Edit board"
        description="Update board settings and gateway."
        isAdmin={isAdmin}
        adminOnlyMessage="Only organization owners and admins can edit board settings."
        mainRef={mainRef}
      >
        <div className="space-y-6">
          <form
            onSubmit={handleSubmit}
            className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
          >
            {resolvedBoardType !== "general" &&
            baseBoard &&
            !(baseBoard.goal_confirmed ?? false) ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-amber-900">
                    Goal needs confirmation
                  </p>
                  <p className="mt-1 text-xs text-amber-800/80">
                    Start onboarding to draft an objective and success metrics.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setIsOnboardingOpen(true)}
                  disabled={isLoading || !baseBoard}
                >
                  Start onboarding
                </Button>
              </div>
            ) : null}
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-900">
                  Board name <span className="text-red-500">*</span>
                </label>
                <Input
                  value={resolvedName}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Board name"
                  disabled={isLoading || !baseBoard}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-900">
                  Gateway <span className="text-red-500">*</span>
                </label>
                <SearchableSelect
                  ariaLabel="Select gateway"
                  value={displayGatewayId}
                  onValueChange={setGatewayId}
                  options={gatewayOptions}
                  placeholder="Select gateway"
                  searchPlaceholder="Search gateways..."
                  emptyMessage="No gateways found."
                  triggerClassName="w-full h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
                  contentClassName="rounded-xl border border-slate-200 shadow-lg"
                  itemClassName="px-4 py-3 text-sm text-slate-700 data-[selected=true]:bg-slate-50 data-[selected=true]:text-slate-900"
                />
              </div>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-900">
                  Board type
                </label>
                <Select value={resolvedBoardType} onValueChange={setBoardType}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select board type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="goal">Goal</SelectItem>
                    <SelectItem value="general">General</SelectItem>
                  </SelectContent>
                </Select>
                <div className="space-y-2 pt-1">
                  <label className="text-sm font-medium text-slate-900">
                    Max worker agents
                  </label>
                  <Input
                    type="number"
                    min={0}
                    step={1}
                    value={resolvedMaxAgents}
                    onChange={(event) => {
                      const next = Number.parseInt(event.target.value, 10);
                      if (Number.isNaN(next)) {
                        setMaxAgents(0);
                        return;
                      }
                      setMaxAgents(Math.max(0, next));
                    }}
                    disabled={isLoading}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-900">
                  Board group
                </label>
                <SearchableSelect
                  ariaLabel="Select board group"
                  value={resolvedBoardGroupId}
                  onValueChange={setBoardGroupId}
                  options={groupOptions}
                  placeholder="No group"
                  searchPlaceholder="Search groups..."
                  emptyMessage="No groups found."
                  triggerClassName="w-full h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
                  contentClassName="rounded-xl border border-slate-200 shadow-lg"
                  itemClassName="px-4 py-3 text-sm text-slate-700 data-[selected=true]:bg-slate-50 data-[selected=true]:text-slate-900"
                  disabled={isLoading}
                />
                <p className="text-xs text-slate-500">
                  Boards in the same group can share cross-board context for
                  agents.
                </p>
              </div>
              {resolvedBoardType !== "general" ? (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-900">
                    Target date
                  </label>
                  <Input
                    type="date"
                    value={resolvedTargetDate}
                    onChange={(event) => setTargetDate(event.target.value)}
                    disabled={isLoading}
                  />
                </div>
              ) : null}
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-900">
                Description <span className="text-red-500">*</span>
              </label>
              <Textarea
                value={resolvedDescription}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What context should the lead agent know?"
                className="min-h-[120px]"
                disabled={isLoading}
              />
            </div>

            {resolvedBoardType !== "general" ? (
              <>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-900">
                    Objective
                  </label>
                  <Textarea
                    value={resolvedObjective}
                    onChange={(event) => setObjective(event.target.value)}
                    placeholder="What should this board achieve?"
                    className="min-h-[120px]"
                    disabled={isLoading}
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-900">
                    Success metrics (JSON)
                  </label>
                  <Textarea
                    value={resolvedSuccessMetrics}
                    onChange={(event) => setSuccessMetrics(event.target.value)}
                    placeholder='e.g. { "target": "Launch by week 2" }'
                    className="min-h-[140px] font-mono text-xs"
                    disabled={isLoading}
                  />
                  <p className="text-xs text-slate-500">
                    Add key outcomes so the lead agent can measure progress.
                  </p>
                  {metricsError ? (
                    <p className="text-xs text-red-500">{metricsError}</p>
                  ) : null}
                </div>
              </>
            ) : null}

            <section className="space-y-3 border-t border-slate-200 pt-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  Rules
                </h2>
                <p className="text-xs text-slate-600">
                  Configure board-level workflow enforcement.
                </p>
              </div>
              <div className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-3">
                <button
                  type="button"
                  role="switch"
                  aria-checked={resolvedRequireApprovalForDone}
                  aria-label="Require approval"
                  onClick={() =>
                    setRequireApprovalForDone(!resolvedRequireApprovalForDone)
                  }
                  disabled={isLoading}
                  className={`mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition ${
                    resolvedRequireApprovalForDone
                      ? "border-emerald-600 bg-emerald-600"
                      : "border-slate-300 bg-slate-200"
                  } ${isLoading ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
                >
                  <span
                    className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition ${
                      resolvedRequireApprovalForDone
                        ? "translate-x-5"
                        : "translate-x-0.5"
                    }`}
                  />
                </button>
                <span className="space-y-1">
                  <span className="block text-sm font-medium text-slate-900">
                    Require approval
                  </span>
                  <span className="block text-xs text-slate-600">
                    Require at least one linked approval in{" "}
                    <code>approved</code> state before a task can be marked{" "}
                    <code>done</code>.
                  </span>
                </span>
              </div>
              <div className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-3">
                <button
                  type="button"
                  role="switch"
                  aria-checked={resolvedRequireReviewBeforeDone}
                  aria-label="Require review before done"
                  onClick={() =>
                    setRequireReviewBeforeDone(!resolvedRequireReviewBeforeDone)
                  }
                  disabled={isLoading}
                  className={`mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition ${
                    resolvedRequireReviewBeforeDone
                      ? "border-emerald-600 bg-emerald-600"
                      : "border-slate-300 bg-slate-200"
                  } ${isLoading ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
                >
                  <span
                    className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition ${
                      resolvedRequireReviewBeforeDone
                        ? "translate-x-5"
                        : "translate-x-0.5"
                    }`}
                  />
                </button>
                <span className="space-y-1">
                  <span className="block text-sm font-medium text-slate-900">
                    Require review before done
                  </span>
                  <span className="block text-xs text-slate-600">
                    Tasks must move to <code>review</code> before they can be
                    marked <code>done</code>.
                  </span>
                </span>
              </div>
              <div className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-3">
                <button
                  type="button"
                  role="switch"
                  aria-checked={resolvedBlockStatusChangesWithPendingApproval}
                  aria-label="Block status changes with pending approval"
                  onClick={() =>
                    setBlockStatusChangesWithPendingApproval(
                      !resolvedBlockStatusChangesWithPendingApproval,
                    )
                  }
                  disabled={isLoading}
                  className={`mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition ${
                    resolvedBlockStatusChangesWithPendingApproval
                      ? "border-emerald-600 bg-emerald-600"
                      : "border-slate-300 bg-slate-200"
                  } ${isLoading ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
                >
                  <span
                    className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition ${
                      resolvedBlockStatusChangesWithPendingApproval
                        ? "translate-x-5"
                        : "translate-x-0.5"
                    }`}
                  />
                </button>
                <span className="space-y-1">
                  <span className="block text-sm font-medium text-slate-900">
                    Block status changes with pending approval
                  </span>
                  <span className="block text-xs text-slate-600">
                    Prevent status transitions while any linked approval is in{" "}
                    <code>pending</code> state.
                  </span>
                </span>
              </div>
              <div className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-3">
                <button
                  type="button"
                  role="switch"
                  aria-checked={resolvedOnlyLeadCanChangeStatus}
                  aria-label="Only lead can change status"
                  onClick={() =>
                    setOnlyLeadCanChangeStatus(!resolvedOnlyLeadCanChangeStatus)
                  }
                  disabled={isLoading}
                  className={`mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition ${
                    resolvedOnlyLeadCanChangeStatus
                      ? "border-emerald-600 bg-emerald-600"
                      : "border-slate-300 bg-slate-200"
                  } ${isLoading ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
                >
                  <span
                    className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition ${
                      resolvedOnlyLeadCanChangeStatus
                        ? "translate-x-5"
                        : "translate-x-0.5"
                    }`}
                  />
                </button>
                <span className="space-y-1">
                  <span className="block text-sm font-medium text-slate-900">
                    Only lead can change status
                  </span>
                  <span className="block text-xs text-slate-600">
                    Restrict status changes to the board lead.
                  </span>
                </span>
              </div>
            </section>

            {gateways.length === 0 ? (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                <p>
                  No gateways available. Create one in Gateways to continue.
                </p>
              </div>
            ) : null}

            {errorMessage ? (
              <p className="text-sm text-red-500">{errorMessage}</p>
            ) : null}

            <div className="flex justify-end gap-3">
              <Button
                type="button"
                variant="ghost"
                onClick={() => router.push(`/boards/${boardId}`)}
                disabled={isLoading}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={isLoading || !baseBoard || !isFormReady}
              >
                {isLoading ? "Saving…" : "Save changes"}
              </Button>
            </div>

            <section className="space-y-4 border-t border-slate-200 pt-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  Webhooks
                </h2>
                <p className="text-xs text-slate-600">
                  Add inbound webhook endpoints so the lead agent can react to
                  external events.
                </p>
              </div>
              <div className="space-y-3 rounded-lg border border-slate-200 px-4 py-4">
                <label className="text-sm font-medium text-slate-900">
                  Lead agent instruction
                </label>
                <Textarea
                  value={webhookDescription}
                  onChange={(event) =>
                    setWebhookDescription(event.target.value)
                  }
                  placeholder="Describe exactly what the lead agent should do when payloads arrive."
                  className="min-h-[90px]"
                  disabled={isLoading || isWebhookBusy}
                />
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-900">
                    Agent
                  </label>
                  <Select
                    value={webhookAgentValue}
                    onValueChange={setWebhookAgentValue}
                    disabled={isLoading || isWebhookBusy}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Lead agent (default fallback)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={LEAD_AGENT_VALUE}>
                        Lead agent (default fallback)
                      </SelectItem>
                      {webhookAgents.map((agent) => (
                        <SelectItem key={agent.id} value={agent.id}>
                          {agent.name}
                          {agent.is_board_lead ? " (lead)" : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex justify-end">
                  <Button
                    type="button"
                    onClick={handleCreateWebhook}
                    disabled={
                      isLoading ||
                      isWebhookBusy ||
                      !baseBoard ||
                      !webhookDescription.trim()
                    }
                  >
                    {createWebhookMutation.isPending
                      ? "Creating webhook…"
                      : "Create webhook"}
                  </Button>
                </div>
              </div>

              {webhookErrorMessage ? (
                <p className="text-sm text-red-500">{webhookErrorMessage}</p>
              ) : null}

              {webhooksQuery.isLoading ? (
                <p className="text-sm text-slate-500">Loading webhooks…</p>
              ) : null}

              {!webhooksQuery.isLoading && webhooks.length === 0 ? (
                <p className="rounded-lg border border-dashed border-slate-300 px-4 py-3 text-sm text-slate-600">
                  No webhooks configured yet.
                </p>
              ) : null}

              <div className="space-y-3">
                {webhooks.map((webhook) => {
                  const isDeletingWebhook = deletingWebhookId === webhook.id;
                  const isUpdatingWebhook = updatingWebhookId === webhook.id;
                  return (
                    <WebhookCard
                      key={webhook.id}
                      webhook={webhook}
                      agents={webhookAgents}
                      isLoading={isLoading}
                      isWebhookCreating={isWebhookCreating}
                      isDeletingWebhook={isDeletingWebhook}
                      isUpdatingWebhook={isUpdatingWebhook}
                      copiedWebhookId={copiedWebhookId}
                      onCopy={handleCopyWebhookEndpoint}
                      onDelete={handleDeleteWebhook}
                      onViewPayloads={handleViewWebhookPayloads}
                      onUpdate={handleUpdateWebhook}
                    />
                  );
                })}
              </div>
            </section>

            <section className="space-y-4 border-t border-slate-200 pt-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  Task Pipelines
                </h2>
                <p className="text-xs text-slate-600">
                  Automatically create tasks on this or another board when a
                  task reaches a specific status. Boards in the same group are
                  shown together.
                </p>
              </div>
              <div className="space-y-3 rounded-lg border border-slate-200 px-4 py-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-900">
                      Target board
                    </label>
                    <Select
                      value={pipelineTargetBoardId}
                      onValueChange={setPipelineTargetBoardId}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select target board" />
                      </SelectTrigger>
                      <SelectContent>
                        {(() => {
                          const grouped = new Map<
                            string,
                            { groupName: string; boards: BoardRead[] }
                          >();
                          const ungrouped: BoardRead[] = [];
                          for (const b of allBoards) {
                            if (b.board_group_id) {
                              const g = groups.find(
                                (gr) => gr.id === b.board_group_id,
                              );
                              const key = b.board_group_id;
                              if (!grouped.has(key)) {
                                grouped.set(key, {
                                  groupName: g?.name ?? "Group",
                                  boards: [],
                                });
                              }
                              grouped.get(key)!.boards.push(b);
                            } else {
                              ungrouped.push(b);
                            }
                          }
                          return (
                            <>
                              {Array.from(grouped.entries()).map(
                                ([key, { groupName, boards: gBoards }]) => (
                                  <div key={key}>
                                    <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                      {groupName}
                                    </p>
                                    {gBoards.map((b) => (
                                      <SelectItem key={b.id} value={b.id}>
                                        {b.name}
                                        {b.id === boardId ? " (this board)" : ""}
                                      </SelectItem>
                                    ))}
                                  </div>
                                ),
                              )}
                              {ungrouped.length > 0 ? (
                                <div>
                                  {grouped.size > 0 ? (
                                    <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                      Ungrouped
                                    </p>
                                  ) : null}
                                  {ungrouped.map((b) => (
                                    <SelectItem key={b.id} value={b.id}>
                                      {b.name}
                                      {b.id === boardId ? " (this board)" : ""}
                                    </SelectItem>
                                  ))}
                                </div>
                              ) : null}
                            </>
                          );
                        })()}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-900">
                      Trigger when status is
                    </label>
                    <Select
                      value={pipelineTriggerStatus}
                      onValueChange={setPipelineTriggerStatus}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="done">Done</SelectItem>
                        <SelectItem value="review">Review</SelectItem>
                        <SelectItem value="in_progress">In Progress</SelectItem>
                        <SelectItem value="inbox">Inbox</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-900">
                    New task title template
                  </label>
                  <Input
                    value={pipelineTitleTemplate}
                    onChange={(e) => setPipelineTitleTemplate(e.target.value)}
                    placeholder='e.g. Video: {{source_task.title}}'
                    disabled={isLoading}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-900">
                    New task description template
                  </label>
                  <Textarea
                    value={pipelineDescriptionTemplate}
                    onChange={(e) =>
                      setPipelineDescriptionTemplate(e.target.value)
                    }
                    placeholder="e.g. Create video from completed script.&#10;Source task: {{source_task.title}}&#10;Details: {{source_task.description}}"
                    className="min-h-[70px]"
                    disabled={isLoading}
                  />
                  <p className="text-xs text-slate-500">
                    Variables:{" "}
                    <code className="text-xs">{"{{source_task.title}}"}</code>,{" "}
                    <code className="text-xs">
                      {"{{source_task.description}}"}
                    </code>
                    ,{" "}
                    <code className="text-xs">{"{{source_board.name}}"}</code>,{" "}
                    <code className="text-xs">
                      {"{{source_task.agent_name}}"}
                    </code>
                    ,{" "}
                    <code className="text-xs">{"{{source_task.id}}"}</code>
                  </p>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-900">
                    Assign to agent (optional)
                  </label>
                  <Select
                    value={pipelineTargetAgentId}
                    onValueChange={setPipelineTargetAgentId}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Lead agent (default)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={LEAD_AGENT_VALUE}>
                        Lead agent (default)
                      </SelectItem>
                      {webhookAgents.map((agent) => (
                        <SelectItem key={agent.id} value={agent.id}>
                          {agent.name}
                          {agent.is_board_lead ? " (lead)" : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Handoff Options
                  </p>
                  <label className="flex items-center gap-2 text-sm text-slate-900">
                    <input
                      type="checkbox"
                      checked={pipelineTransferFiles}
                      onChange={(e) =>
                        setPipelineTransferFiles(e.target.checked)
                      }
                      className="h-4 w-4 rounded border-slate-300"
                    />
                    Transfer workspace files to target agent
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-900">
                    <input
                      type="checkbox"
                      checked={pipelineNotifyAgent}
                      onChange={(e) =>
                        setPipelineNotifyAgent(e.target.checked)
                      }
                      className="h-4 w-4 rounded border-slate-300"
                    />
                    Send prompt/instructions to target agent
                  </label>
                  {pipelineNotifyAgent ? (
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-900">
                        Notification prompt
                      </label>
                      <Textarea
                        value={pipelineNotificationTemplate}
                        onChange={(e) =>
                          setPipelineNotificationTemplate(e.target.value)
                        }
                        placeholder="e.g. A script has been completed by {{source_task.agent_name}}. Read the files in pipeline-inputs/ and create a video. Task: {{source_task.title}}"
                        className="min-h-[70px]"
                        disabled={isLoading}
                      />
                      <p className="text-xs text-slate-500">
                        Same template variables as above. Transferred file list
                        is appended automatically.
                      </p>
                    </div>
                  ) : null}
                </div>
                <div className="flex justify-end">
                  <Button
                    type="button"
                    onClick={handleCreatePipeline}
                    disabled={
                      isLoading ||
                      createPipelineMutation.isPending ||
                      !pipelineTargetBoardId ||
                      !pipelineTitleTemplate.trim()
                    }
                  >
                    {createPipelineMutation.isPending
                      ? "Creating pipeline…"
                      : "Create pipeline"}
                  </Button>
                </div>
              </div>

              {pipelineError ? (
                <p className="text-sm text-red-500">{pipelineError}</p>
              ) : null}

              {pipelinesQuery.isLoading ? (
                <p className="text-sm text-slate-500">Loading pipelines…</p>
              ) : null}

              {!pipelinesQuery.isLoading && pipelines.length === 0 ? (
                <p className="rounded-lg border border-dashed border-slate-300 px-4 py-3 text-sm text-slate-600">
                  No pipelines configured yet. Tasks will stop on this board by
                  default.
                </p>
              ) : null}

              <div className="space-y-3">
                {pipelines.map((pipeline) => {
                  const targetBoard = allBoards.find(
                    (b) => b.id === pipeline.target_board_id,
                  );
                  const isSameBoard = pipeline.target_board_id === boardId;
                  const isEditing = editingPipelineId === pipeline.id;

                  if (isEditing && editPipelineData) {
                    return (
                      <div
                        key={pipeline.id}
                        className="space-y-3 rounded-lg border-2 border-blue-300 bg-blue-50/30 px-4 py-4"
                      >
                        <p className="text-sm font-semibold text-slate-900">
                          Edit Pipeline
                        </p>
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                          <div className="space-y-2">
                            <label className="text-sm font-medium text-slate-900">
                              Target board
                            </label>
                            <Select
                              value={editPipelineData.target_board_id}
                              onValueChange={(v) =>
                                setEditPipelineData({
                                  ...editPipelineData,
                                  target_board_id: v,
                                })
                              }
                            >
                              <SelectTrigger>
                                <SelectValue placeholder="Select board" />
                              </SelectTrigger>
                              <SelectContent>
                                {allBoards.map((b) => (
                                  <SelectItem key={b.id} value={b.id}>
                                    {b.name}
                                    {b.id === boardId ? " (this board)" : ""}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-2">
                            <label className="text-sm font-medium text-slate-900">
                              Trigger when status is
                            </label>
                            <Select
                              value={editPipelineData.trigger_status}
                              onValueChange={(v) =>
                                setEditPipelineData({
                                  ...editPipelineData,
                                  trigger_status: v,
                                })
                              }
                            >
                              <SelectTrigger>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="done">Done</SelectItem>
                                <SelectItem value="review">Review</SelectItem>
                                <SelectItem value="in_progress">
                                  In Progress
                                </SelectItem>
                                <SelectItem value="inbox">Inbox</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                        </div>
                        <div className="space-y-2">
                          <label className="text-sm font-medium text-slate-900">
                            New task title template
                          </label>
                          <Input
                            value={editPipelineData.task_title_template}
                            onChange={(e) =>
                              setEditPipelineData({
                                ...editPipelineData,
                                task_title_template: e.target.value,
                              })
                            }
                            placeholder='e.g. Video: {{source_task.title}}'
                          />
                        </div>
                        <div className="space-y-2">
                          <label className="text-sm font-medium text-slate-900">
                            New task description template
                          </label>
                          <Textarea
                            value={editPipelineData.task_description_template}
                            onChange={(e) =>
                              setEditPipelineData({
                                ...editPipelineData,
                                task_description_template: e.target.value,
                              })
                            }
                            placeholder="e.g. Create video from completed script.&#10;Source task: {{source_task.title}}&#10;Details: {{source_task.description}}"
                            className="min-h-[70px]"
                          />
                          <p className="text-xs text-slate-500">
                            Variables:{" "}
                            <code className="text-xs">
                              {"{{source_task.title}}"}
                            </code>
                            ,{" "}
                            <code className="text-xs">
                              {"{{source_task.description}}"}
                            </code>
                            ,{" "}
                            <code className="text-xs">
                              {"{{source_board.name}}"}
                            </code>
                            ,{" "}
                            <code className="text-xs">
                              {"{{source_task.agent_name}}"}
                            </code>
                            ,{" "}
                            <code className="text-xs">
                              {"{{source_task.id}}"}
                            </code>
                          </p>
                        </div>
                        <div className="space-y-2">
                          <label className="text-sm font-medium text-slate-900">
                            Assign to agent (optional)
                          </label>
                          <Select
                            value={editPipelineData.target_agent_id}
                            onValueChange={(v) =>
                              setEditPipelineData({
                                ...editPipelineData,
                                target_agent_id: v,
                              })
                            }
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Lead agent (default)" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={LEAD_AGENT_VALUE}>
                                Lead agent (default)
                              </SelectItem>
                              {webhookAgents.map((agent) => (
                                <SelectItem key={agent.id} value={agent.id}>
                                  {agent.name}
                                  {agent.is_board_lead ? " (lead)" : ""}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                            Handoff Options
                          </p>
                          <label className="flex items-center gap-2 text-sm text-slate-900">
                            <input
                              type="checkbox"
                              checked={editPipelineData.transfer_files}
                              onChange={(e) =>
                                setEditPipelineData({
                                  ...editPipelineData,
                                  transfer_files: e.target.checked,
                                })
                              }
                              className="h-4 w-4 rounded border-slate-300"
                            />
                            Transfer workspace files to target agent
                          </label>
                          <label className="flex items-center gap-2 text-sm text-slate-900">
                            <input
                              type="checkbox"
                              checked={editPipelineData.notify_agent}
                              onChange={(e) =>
                                setEditPipelineData({
                                  ...editPipelineData,
                                  notify_agent: e.target.checked,
                                })
                              }
                              className="h-4 w-4 rounded border-slate-300"
                            />
                            Send prompt/instructions to target agent
                          </label>
                          {editPipelineData.notify_agent ? (
                            <div className="space-y-2">
                              <label className="text-sm font-medium text-slate-900">
                                Notification prompt
                              </label>
                              <Textarea
                                value={
                                  editPipelineData.notification_template
                                }
                                onChange={(e) =>
                                  setEditPipelineData({
                                    ...editPipelineData,
                                    notification_template: e.target.value,
                                  })
                                }
                                placeholder="e.g. A script has been completed. Read pipeline-inputs/ and create a video."
                                className="min-h-[70px]"
                              />
                              <p className="text-xs text-slate-500">
                                Same template variables. Transferred file list
                                appended automatically.
                              </p>
                            </div>
                          ) : null}
                        </div>
                        <div className="flex justify-end gap-2">
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={handleCancelEditPipeline}
                          >
                            Cancel
                          </Button>
                          <Button
                            type="button"
                            onClick={handleSaveEditPipeline}
                            disabled={
                              updatePipelineMutation.isPending ||
                              !editPipelineData.target_board_id ||
                              !editPipelineData.task_title_template.trim()
                            }
                          >
                            {updatePipelineMutation.isPending
                              ? "Saving…"
                              : "Save"}
                          </Button>
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div
                      key={pipeline.id}
                      className="space-y-2 rounded-lg border border-slate-200 px-4 py-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-slate-900">
                            When{" "}
                            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium">
                              {pipeline.trigger_status}
                            </span>{" "}
                            → create task on{" "}
                            <span className="font-semibold text-blue-700">
                              {targetBoard?.name ?? "Unknown board"}
                            </span>
                            {isSameBoard ? (
                              <span className="ml-1 text-xs text-slate-500">
                                (this board)
                              </span>
                            ) : null}
                          </span>
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                              pipeline.enabled
                                ? "bg-emerald-100 text-emerald-700"
                                : "bg-slate-100 text-slate-500"
                            }`}
                          >
                            {pipeline.enabled ? "Enabled" : "Disabled"}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={() => handleStartEditPipeline(pipeline)}
                          >
                            Edit
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={() =>
                              handleTogglePipeline(
                                pipeline.id,
                                !pipeline.enabled,
                              )
                            }
                            disabled={togglePipelineMutation.isPending}
                          >
                            {pipeline.enabled ? "Disable" : "Enable"}
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={() => handleDeletePipeline(pipeline.id)}
                            disabled={deletePipelineMutation.isPending}
                          >
                            Delete
                          </Button>
                        </div>
                      </div>
                      <p className="text-xs text-slate-600">
                        Title: {pipeline.task_title_template || "—"}
                      </p>
                      {pipeline.task_description_template ? (
                        <p className="text-xs text-slate-500 line-clamp-2">
                          Description: {pipeline.task_description_template}
                        </p>
                      ) : null}
                      {(pipeline.transfer_files || pipeline.notify_agent) ? (
                        <div className="flex gap-2 pt-1">
                          {pipeline.transfer_files ? (
                            <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">
                              Files
                            </span>
                          ) : null}
                          {pipeline.notify_agent ? (
                            <span className="inline-flex items-center rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-semibold text-purple-700">
                              Notify
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </section>
          </form>
        </div>
      </DashboardPageLayout>
      <Dialog open={isOnboardingOpen} onOpenChange={setIsOnboardingOpen}>
        <DialogContent
          aria-label="Board onboarding"
          onPointerDownOutside={(event) => event.preventDefault()}
          onInteractOutside={(event) => event.preventDefault()}
        >
          <div className="flex">
            <DialogClose asChild>
              <button
                type="button"
                className="sticky top-4 z-10 ml-auto rounded-lg border border-slate-200 bg-[color:var(--surface)] p-2 text-slate-500 transition hover:bg-slate-50"
                aria-label="Close onboarding"
              >
                <X className="h-4 w-4" />
              </button>
            </DialogClose>
          </div>
          {boardId ? (
            <BoardOnboardingChat
              boardId={boardId}
              onConfirmed={handleOnboardingConfirmed}
            />
          ) : (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
              Unable to start onboarding.
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
