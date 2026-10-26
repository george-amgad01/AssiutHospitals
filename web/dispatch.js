/* Assiut Emergency Dispatch dashboard.
 * Keeps the existing /api/dispatch contract and animates a marker along
 * the exact geometry returned by the route algorithm. Animation is a visual
 * simulation, not live GPS tracking.
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

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 19
}).addTo(map);

  var bounds = L.latLngBounds(NET.bounds || [[27.17, 31.16], [27.205, 31.205]]);
  map.fitBounds(bounds.pad(0.03));

  if (NET.roads && NET.roads.length) {
    L.polyline(NET.roads, {
      color: "#34536d", weight: 1.5, opacity: 0.78, interactive: false
    }).addTo(map);
  }

  var hospitalLayer = L.layerGroup().addTo(map);
  var startLayer = L.layerGroup().addTo(map);
  var routeLayer = L.layerGroup().addTo(map);
  var animationFrame = null;
  var animationMarker = null;
  var routeLine = null;
  var origin = null;

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  (HOSP.hospitals || []).forEach(function (h) {
    if (typeof h.lat !== "number" || typeof h.lon !== "number") return;
    var marker = L.circleMarker([h.lat, h.lon], {
      radius: 5.5, color: "#39151d", weight: 1.2,
      fillColor: "#ff5c67", fillOpacity: 0.98
    });
    marker.bindPopup("<b>" + esc(h.display_name) + "</b><br>" +
      h.lat.toFixed(6) + ", " + h.lon.toFixed(6));
    marker.bindTooltip(esc(h.display_name), { direction: "top", offset: [0, -6] });
    marker.addTo(hospitalLayer);
  });

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
    distance: document.getElementById("r-distance"),
    meta: document.getElementById("r-meta"),
    route: document.getElementById("r-route"),
    badge: document.getElementById("data-badge")
  };

  function setStatus(message, isError) {
    els.status.textContent = message;
    els.status.className = isError ? "error" : "";
  }

  function stopAnimation() {
    if (animationFrame !== null) {
      cancelAnimationFrame(animationFrame);
      animationFrame = null;
    }
    if (animationMarker) {
      routeLayer.removeLayer(animationMarker);
      animationMarker = null;
    }
  }

  function clearRoute() {
    stopAnimation();
    routeLayer.clearLayers();
    routeLine = null;
  }

  function ambulanceIcon() {
    return L.divIcon({
      className: "",
      html: '<div class="ambulance-icon" aria-label="Simulated ambulance">🚑</div>',
      iconSize: [34, 34],
      iconAnchor: [17, 17]
    });
  }

  function setOrigin(lat, lon) {
    origin = { lat: lat, lon: lon };
    els.lat.value = lat.toFixed(6);
    els.lon.value = lon.toFixed(6);
    startLayer.clearLayers();
    L.circleMarker([lat, lon], {
      radius: 7, color: "#eafaff", weight: 2,
      fillColor: "#4bdcff", fillOpacity: 1
    }).bindTooltip("Ambulance origin", { direction: "top", offset: [0, -8] })
      .addTo(startLayer);
    setStatus("Origin set. Choose a specialty and find the fastest hospital.");
  }

  /* Linear interpolation over the returned route geometry.
     geometry is expected to be an array of [latitude, longitude] points. */
  function animateAlongRoute(geometry) {
    stopAnimation();
    if (!Array.isArray(geometry) || geometry.length < 2) return;

    var points = geometry.map(function (p) {
      return L.latLng(Number(p[0]), Number(p[1]));
    }).filter(function (p) {
      return Number.isFinite(p.lat) && Number.isFinite(p.lng);
    });
    if (points.length < 2) return;

    var cumulative = [0];
    var total = 0;
    for (var i = 1; i < points.length; i++) {
      total += map.distance(points[i - 1], points[i]);
      cumulative.push(total);
    }
    if (!total) return;

    animationMarker = L.marker(points[0], {
      icon: ambulanceIcon(), interactive: true, zIndexOffset: 1200
    }).bindTooltip("Ambulance route simulation", { direction: "top", offset: [0, -16] })
      .addTo(routeLayer);

    var duration = Math.max(7000, Math.min(18000, total * 18));
    var startTime = null;

    function step(timestamp) {
      if (startTime === null) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      var targetDistance = total * progress;
      var segment = 1;

      while (segment < cumulative.length - 1 && cumulative[segment] < targetDistance) {
        segment++;
      }

      var before = cumulative[segment - 1];
      var span = cumulative[segment] - before;
      var fraction = span > 0 ? (targetDistance - before) / span : 0;
      var a = points[segment - 1];
      var b = points[segment];
      var position = L.latLng(
        a.lat + (b.lat - a.lat) * fraction,
        a.lng + (b.lng - a.lng) * fraction
      );
      animationMarker.setLatLng(position);

      if (progress < 1) {
        animationFrame = requestAnimationFrame(step);
      } else {
        animationFrame = null;
        setStatus("Route calculated. Ambulance route animation completed.");
      }
    }
    animationFrame = requestAnimationFrame(step);
  }

  function showResult(data) {
    els.result.style.display = "block";
    var optimal = data && data.optimal;
    if (!optimal || !optimal.route) {
      els.name.textContent = "No suitable hospital found";
      els.zone.textContent = "Search scope: start zone " + (data.search_zone || "-");
      els.time.textContent = "—";
      els.distance.textContent = "—";
      els.meta.textContent = "";
      els.route.textContent = "";
      return;
    }

    els.name.textContent = optimal.hospital || "Selected hospital";
    els.zone.textContent = "Start zone " + (data.search_zone || optimal.zone || "-") +
      " · Hospital zone " + (optimal.zone || "-");
    els.time.textContent = Number(optimal.seconds || 0).toFixed(1);
    els.distance.textContent = Math.round(Number(optimal.route.length_m || 0)).toLocaleString();
    els.meta.textContent = (optimal.route.edges || []).length + " road edges · Search completed in " +
      Number(data.runtime_seconds || 0).toFixed(3) + " s";
    els.route.textContent = "Route edges: " + ((optimal.route.edges || []).join(" → ") || "Not provided");

    clearRoute();
    var geometry = optimal.route.geometry || [];
    if (geometry.length > 1) {
      routeLine = L.polyline(geometry, {
        color: "#ff5c67", weight: 5, opacity: 0.95,
        lineJoin: "round", lineCap: "round"
      }).addTo(routeLayer);
      L.polyline(geometry, {
        color: "#ffd4d8", weight: 1.2, opacity: 0.9,
        dashArray: "3 9", interactive: false
      }).addTo(routeLayer);
      map.fitBounds(routeLine.getBounds().pad(0.25), { maxZoom: 16 });
      animateAlongRoute(geometry);
      setStatus("Fastest route calculated. Showing simulated ambulance movement.");
    } else {
      setStatus("Hospital selected, but the API returned no route geometry.", true);
    }
  }

  function runSearch() {
    var lat = parseFloat(els.lat.value);
    var lon = parseFloat(els.lon.value);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setStatus("Set the ambulance origin first (click the map or enter latitude/longitude).", true);
      return;
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setStatus("Latitude/longitude are out of range.", true);
      return;
    }

    origin = { lat: lat, lon: lon };
    clearRoute();
    els.result.style.display = "none";
    startLayer.clearLayers();
    L.circleMarker([lat, lon], {
      radius: 7, color: "#eafaff", weight: 2,
      fillColor: "#4bdcff", fillOpacity: 1
    }).bindTooltip("Ambulance origin", { direction: "top", offset: [0, -8] })
      .addTo(startLayer);

    var specialty = els.specialty.value || "general";
    var url = "/api/dispatch?lat=" + encodeURIComponent(lat) +
      "&lon=" + encodeURIComponent(lon) +
      "&specialty=" + encodeURIComponent(specialty);

    els.search.disabled = true;
    setStatus("Searching the start zone for the fastest suitable hospital...");
    fetch(url)
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (outcome) {
        if (!outcome.ok) throw new Error(outcome.body.error || "Dispatch request failed.");
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
    clearRoute();
    els.result.style.display = "none";
    els.status.className = "";
    els.status.textContent = "Click the map to set the ambulance start.";
  });

  fetch("/api/dispatch/meta")
    .then(function (response) {
      if (!response.ok) throw new Error("Metadata request failed.");
      return response.json();
    })
    .then(function (meta) {
      (meta.specialties || []).forEach(function (specialty) {
        var option = document.createElement("option");
        option.value = specialty;
        option.textContent = specialty.replace(/_/g, " ").replace(/\b\w/g, function (c) {
          return c.toUpperCase();
        });
        els.specialty.appendChild(option);
      });
      if (!els.specialty.options.length) {
        var fallback = document.createElement("option");
        fallback.value = "general";
        fallback.textContent = "General";
        els.specialty.appendChild(fallback);
      }
      var messages = [];
      if (meta.synthetic) messages.push("SYNTHETIC EMERGENCY DATA");
      if (String(meta.search_scope || "") === "start_zone_only") messages.push("START-ZONE-ONLY SEARCH");
      if (messages.length) {
        els.badge.textContent = "⚠ " + messages.join(" · ");
        els.badge.style.display = "inline-flex";
      }
      if (meta.config_errors && meta.config_errors.length) {
        setStatus("Configuration error: " + meta.config_errors[0], true);
      }
    })
    .catch(function () {
      setStatus("Could not load dispatch metadata. Check that the server is running.", true);
    });
})();