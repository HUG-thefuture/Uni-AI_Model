/* global $ */
/* 收银台页逻辑:订单展示 → 沙箱模拟支付 / 支付宝跳转+轮询 → 成功态。
   order_no 由收银台跳转参数携带;未登录时 api.js 会自动跳转登录页。 */
(function () {
  'use strict';

  const orderNo = new URLSearchParams(location.search).get('order_no') || '';
  let order = null;
  let pollTimer = null;

  const $amount = $('#pay-amount');
  const $orderNo = $('#pay-order-no');
  const $method = $('#pay-method');
  const $status = $('#pay-status');
  const $tip = $('#pay-tip');
  const $actions = $('#pay-actions');
  const $error = $('#pay-error');
  const $count = $('#pay-count');

  function setStatus(status) {
    $status
      .removeClass('pending paid')
      .addClass(status === 'paid' ? 'paid' : 'pending')
      .text(status === 'paid' ? '已支付' : '待支付');
  }

  function render() {
    $amount.text(`${order.amount} 元`);
    $orderNo.text(order.order_no);
    $method.text(order.payment_method === 'alipay' ? '支付宝(沙箱)' : '模拟收银台');
    setStatus(order.status);
    if (order.status === 'paid') return renderSuccess();
    renderActions();
  }

  function renderSuccess() {
    $('#success-points').text(`+¥${Number(order.amount).toFixed(2)}`);
    $('#pay-detail').hide();
    $('#pay-success').removeAttr('hidden');
    stopPolling();
  }

  function showError(message) {
    $error.text(message || '操作失败,请稍后重试');
  }

  function renderActions() {
    $actions.empty();
    if (order.payment_method === 'alipay') {
      $tip.text('点击下方按钮跳转支付宝沙箱收银台完成支付；支付完成后请回到本页，系统会自动确认到账。');
      $actions.append(
        $('<button class="btn-block btn-pay" type="button">跳转支付宝收银台</button>')
          .on('click', () => { window.location.href = order.pay_url; }),
        $('<button class="btn-block btn-goto" type="button">我已完成支付,确认到账</button>')
          .on('click', syncOrder)
      );
      startPolling();
    } else {
      $tip.text('当前为内置模拟收银台(未配置支付宝沙箱密钥)。点击「确认支付」即可模拟真实支付回调完成入账,用于演示完整支付闭环。');
      $actions.append(
        $('<button class="btn-block btn-pay" type="button">确认支付(沙箱模拟)</button>')
          .on('click', mockPay)
      );
    }
  }

  function mockPay() {
    $error.text('');
    window.PortalApi.request({
      url: `/api/wallet/orders/${encodeURIComponent(orderNo)}/mock-pay`,
      method: 'POST'
    }).then((data) => {
      if (data && data.status === 'paid') {
        order.status = 'paid';
        render();
      }
    }).catch((err) => showError(err.message));
  }

  function syncOrder() {
    $error.text('');
    window.PortalApi.request({
      url: `/api/wallet/orders/${encodeURIComponent(orderNo)}/sync`,
      method: 'POST'
    }).then((data) => {
      if (data && data.status === 'paid') {
        order.status = 'paid';
        render();
      } else {
        showError('尚未查询到支付结果,若已支付请稍后再次点击确认。');
      }
    }).catch((err) => showError(err.message));
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(() => {
      loadOrder(true);
    }, 5000);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    $count.text('');
  }

  function loadOrder(silent) {
    if (!orderNo) {
      if (!silent) showError('缺少订单号参数,请从个人中心重新发起充值。');
      return;
    }
    window.PortalApi.request({
      url: `/api/wallet/orders/${encodeURIComponent(orderNo)}`
    }).then((data) => {
      order = Object.assign({}, order, data);
      if (!silent) {
        render();
      } else if (order.status === 'paid') {
        render();
      }
    }).catch((err) => {
      if (!silent) showError(err.message);
    });
  }

  $(function () {
    if (!orderNo) {
      showError('缺少订单号参数,请从个人中心重新发起充值。');
      return;
    }
    loadOrder(false);
  });
}());
