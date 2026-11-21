import { useEffect, useState } from "react";
import { getResourceActivities } from "./services/resourceTrackingApi";

export default function ResourceTrackingRows() {
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadResources() {
      try {
        const result = await getResourceActivities();

        if (active) {
          setResources(result.resources || []);
          setError("");
        }
      } catch (err) {
        if (active) {
          setError(err.message);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadResources();

    const interval = setInterval(loadResources, 60000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  if (loading) {
    return (
      <tbody>
        <tr>
          <td colSpan={8} className="empty-resource">
            Loading AWS resources...
          </td>
        </tr>
      </tbody>
    );
  }

  if (error) {
    return (
      <tbody>
        <tr>
          <td colSpan={8} className="empty-resource">
            Unable to load resources: {error}
          </td>
        </tr>
      </tbody>
    );
  }

  if (resources.length === 0) {
    return (
      <tbody>
        <tr>
          <td colSpan={8} className="empty-resource">
            No AWS resources collected yet.
          </td>
        </tr>
      </tbody>
    );
  }

  return (
    <tbody>
      {resources.map((resource) => (
        <tr key={resource.id}>
          <td>{resource.resource_id}</td>
          <td>{resource.service_code}</td>
          <td>{resource.created_by || "Unknown"}</td>
          <td>{resource.account_name || resource.account_id}</td>
          <td>{resource.region || "—"}</td>
          <td>
            {resource.created_at
              ? new Date(resource.created_at).toLocaleString()
              : "Unknown"}
          </td>
          <td>—</td>
          <td>{resource.resource_status || "unknown"}</td>
        </tr>
      ))}
    </tbody>
  );
}
