// Call the dataTables jQuery plugin
$(document).ready(function() {
  $('#dataTable').DataTable({
    ajax: {url: "/admin-api/get-table-data",
    type: "GET",
    dataSrc: ''
  },
    columns: [
      {data: "Name"},
      {data: "Time"},
      {data: "Description"}
    ]
  });
});
