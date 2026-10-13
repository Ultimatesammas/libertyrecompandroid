#pragma once
#include <cstdint>

namespace rex::graphics::gta4_native::adaptive_frame_budget {
// Unlocked has no requested budget. Retain the legacy 30 Hz policy there.
constexpr uint32_t TargetFps(uint32_t limit) noexcept {
  return limit == 30 || limit == 40 || limit == 60 || limit == 120 ? limit : 30;
}
constexpr double DropBelowFps(uint32_t limit) noexcept {
  return 0.90 * TargetFps(limit);
}
constexpr double RecoverAtFps(uint32_t limit) noexcept {
  return 0.95 * TargetFps(limit);
}
constexpr double GuardSlowAboveMs(uint32_t limit) noexcept {
  return 36.0 * 30.0 / TargetFps(limit);
}
constexpr double GuardFastAtMs(uint32_t limit) noexcept {
  return 34.5 * 30.0 / TargetFps(limit);
}
}  // namespace rex::graphics::gta4_native::adaptive_frame_budget
