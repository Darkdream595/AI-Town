/**
 * UI Render Projection 类型
 *
 * 符合 DOC-RENDER-009 规范，由 Backend/Orchestrator 提供的已授权只读 UI 数据
 */

export interface UiRenderProjection {
  protocol_version: 'ui.v1';
  world_id: string;
  revision: number;
  game_time: number; // 游戏分钟数

  hud: HudProjection;
  dialogue?: DialogueProjection;
  mayor_panel?: MayorPanelProjection;
}

export interface HudProjection {
  player_name: string;
  season: string;  // 季节显示（如 "春季"）
  weather: string; // 天气显示（如 "晴朗"）
  time_display: string; // 格式化时间（如 "第0年1月1日 12:00"）
}

export interface DialogueProjection {
  conversation_id: string;
  speaker_name: string;
  speaker_entity_id: string;
  text: string;
  emotion?: string;
  options?: DialogueOption[];
}

export interface DialogueOption {
  option_id: string;
  text: string;
  enabled: boolean;
}

export interface MayorPanelProjection {
  budget_copper: number;
  population: number;
  satisfaction: number; // 0-100
  available_commands: MayorCommand[];
}

export interface MayorCommand {
  command_id: string;
  display_name: string;
  description: string;
  cost_copper: number;
}
