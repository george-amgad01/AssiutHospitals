/* Assiut emergency dispatch - minimal map (requirement 1).
 *
 * Shows ONLY the real SUMO road network and the hospitals at their real
 * coordinates.  Clicking the map sets the ambulance start; the search button
 * asks the server for the fastest suitable hospital and draws its route.
 *
 * خريطة الإرسال: تعرض شبكة الطرق الحقيقية والمستشفيات بإحداثياتها فقط،
 * والنقر يحدد نقطة انطلاق الإسعاف ثم يُرسم المسار الأسرع.
 */
(function () {
  "use strict";

  var NET = window.ASSIUT_NETWORK || { roads: [], bounds: null };
  var HOSP = window.ASSIUT_HOSPITALS || { hospitals: [] };

  var map = L.map("map", {
    zoomControl: true,
    attributionControl: true,
    preferCanvas: true
  });

  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 19
  }).addTo(map);

  var bounds = L.latLngBounds(NET.bounds || [[27.17, 31.16], [27.205, 31.205]]);
  map.fitBounds(bounds.pad(0.03));

  /* The real road network: every edge polyline, nothing else. */
  if (NET.roads && NET.roads.length) {
    L.polyline(NET.roads, {
      color: "#31506b",
      weight: 1.6,
      opacity: 0.85,
      interactive: false
    }).addTo(map);
  }

  var hospitalLayer = L.layerGroup().addTo(map);
  var startLayer = L.layerGroup().addTo(map);
  var routeLayer = L.layerGroup().addTo(map);

  /**
   * Escape text before inserting it into a popup.
   * تأمين النص قبل إدراجه في النافذة المنبثقة.
   */
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* Hospitals: real coordinates only. */
  (HOSP.hospitals || []).forEach(function (h) {
    if (typeof h.lat !== "number" || typeof h.lon !== "number") return;
    var marker = L.circleMarker([h.lat, h.lon], {
      radius: 5.5,
      color: "#2a0d0d",
      weight: 1,
      fillColor: "#e74c3c",
      fillOpacity: 0.95
    });
    marker.bindPopup(
      "<b>" + esc(h.display_name) + "</b><br>" +
      h.lat.toFixed(6) + ", " + h.lon.toFixed(6)
    );
    marker.bindTooltip(esc(h.display_name), { direction: "top", offset: [0, -6] });
    marker.addTo(hospitalLayer);
  });

  var startMarker = null;
  var routeLine = null;
  var origin = null;

  var els = {
    specialty: document.getElementById("specialty"),
    lat: document.getElementById("lat"),
    lon: document.getElementById("lon"),
    search: document.getElementById("search"),
    clear: document.getElementById("clear"),
    status: document.getElementById("status"),
    result: document.getElementById("result"),
    name: document.getElementById("r-name"),
    zone: document.getElementById("r-zone"),
    time: document.getElementById("r-time"),
    meta: document.getElementById("r-meta"),
    route: document.getElementById("r-route"),
    badge: document.getElementById("data-badge")
  };

  /**
   * Put the ambulance start marker at a coordinate and mirror it in the inputs.
   * تعيين نقطة انطلاق الإسعاف وعرض إحداثياتها في الحقول.
   */
  function setOrigin(lat, lon) {
    origin = { lat: lat, lon: lon };
    els.lat.value = lat.toFixed(6);
    els.lon.value = lon.toFixed(6);
    startLayer.clearLayers();
    startMarker = L.circleMarker([lat, lon], {
      radius: 8,
      color: "#ffffff",
      weight: 2,
      fillColor: "#2f80ed",
      fillOpacity: 1
    }).addTo(startLayer);
    startMarker.bindTooltip("ambulance start", { direction: "top", offset: [0, -8] });
    setStatus("Start set. Choose a specialty and press the button.");
  }

  /**
   * Show a status line (and style it as an error when needed).
   * عرض رسالة الحالة وتلوينها عند الخطأ.
   */
  function setStatus(text, isError) {
    els.status.textContent = text;
    els.status.className = isError ? "error" : "";
  }

  /**
   * Draw the returned route and present the optimal hospital.
   * رسم المسار الأمثل وعرض اسم المستشفى والزمن المتوقع.
   */
  function showResult(data) {
    els.result.style.display = "block";
    if (!data.optimal || !data.optimal.route) {
      els.name.textContent = "No suitable hospital";
      els.zone.textContent = "Searched only the start zone: " + (data.search_zone || "-");
      els.time.textContent = "-";
      els.meta.textContent = "";
      els.route.textContent = "";
      return;
    }
    var optimal = data.optimal;
    els.name.textContent = optimal.hospital;
    els.zone.textContent =
      "Start zone " + (data.search_zone || optimal.zone) +
      " - hospital in " + optimal.zone;
    els.time.textContent = optimal.seconds.toFixed(1);
    els.meta.textContent =
      Math.round(optimal.route.length_m) + " m - " +
      optimal.route.edges.length + " road edges - " +
      "search " + data.runtime_seconds.toFixed(3) + " s";
    els.route.textContent = optimal.route.edges.join(" > ");

    routeLayer.clearLayers();
    var geometry = optimal.route.geometry || [];
    if (geometry.length > 1) {
      routeLine = L.polyline(geometry, {
        color: "#ff4d4f",
        weight: 5,
        opacity: 0.95,
        lineJoin: "round"
      }).addTo(routeLayer);
      map.fitBounds(routeLine.getBounds().pad(0.25));
    }
  }

  /**
   * Ask the server for the fastest suitable hospital from the current start.
   * طلب أسرع مستشفى مناسب من الخادم انطلاقاً من النقطة الحالية.
   */
  function runSearch() {
    var lat = parseFloat(els.lat.value);
    var lon = parseFloat(els.lon.value);
    if (!isFinite(lat) || !isFinite(lon)) {
      setStatus("Set the start first (click the map or type lat/lon).", true);
      return;
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setStatus("Latitude/longitude are out of range.", true);
      return;
    }
    origin = { lat: lat, lon: lon };
    routeLayer.clearLayers();
    els.result.style.display = "none";
    startLayer.clearLayers();
    L.circleMarker([lat, lon], {
      radius: 8,
      color: "#ffffff",
      weight: 2,
      fillColor: "#2f80ed",
      fillOpacity: 1
    }).addTo(startLayer);

    var specialty = els.specialty.value || "general";
    var url = "/api/dispatch?lat=" + encodeURIComponent(lat) +
      "&lon=" + encodeURIComponent(lon) +
      "&specialty=" + encodeURIComponent(specialty);

    els.search.disabled = true;
    setStatus("Searching only the zone containing the start point...");
    fetch(url)
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (outcome) {
        if (!outcome.ok) {
          throw new Error(outcome.body.error || "dispatch request failed");
        }
        setStatus("Done.");
        showResult(outcome.body);
      })
      .catch(function (error) {
        setStatus(error.message || String(error), true);
      })
      .finally(function () {
        els.search.disabled = false;
      });
  }

  map.on("click", function (event) {
    setOrigin(event.latlng.lat, event.latlng.lng);
  });

  els.search.addEventListener("click", runSearch);
  els.clear.addEventListener("click", function () {
    origin = null;
    startLayer.clearLayers();
    routeLayer.clearLayers();
    els.result.style.display = "none";
    els.status.className = "";
    els.status.textContent = "Click the map to set the ambulance start.";
  });

  /* Metadata: specialty list + honest provenance of the capacity data. */
  fetch("/api/dispatch/meta")
    .then(function (response) { return response.json(); })
    .then(function (meta) {
      (meta.specialties || []).forEach(function (specialty) {
        var option = document.createElement("option");
        option.value = specialty;
        option.textContent = specialty;
        els.specialty.appendChild(option);
      });
      var messages = [];
      if (meta.synthetic) messages.push("SYNTHETIC emergency data");
      if (String(meta.search_scope || "") === "start_zone_only") {
        messages.push("start-zone-only search");
      }
      if (messages.length) {
        els.badge.textContent = messages.join(" - ");
        els.badge.style.display = "inline-block";
      }
      if (meta.config_errors && meta.config_errors.length) {
        setStatus("Configuration error: " + meta.config_errors[0], true);
      }
    })
    .catch(function () {
      setStatus("Could not load dispatch metadata.", true);
    });
})();
